"""스케줄러: 정해진 시간에 자동으로 데이터 수집 + LLM 분석."""

import asyncio
import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session
from app.models import Favorite, Stock
from app.models.news import News
from app.collectors.stock_price import sync_prices
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.disclosure import sync_disclosures
from app.collectors.exchange_rate import sync_exchange_rates
from app.services.analyst.cost import can_proceed
from app.services.analyst.dedup import unique_favorite_tickers
from app.services.analyst.engine import analyze
from app.services.llm.adapter import get_adapter
from app.services.llm.analyzer import analyze_stock
from app.services.ontology import (
    extract_news_relations_for_universe,
    extract_sec_contracts_for_universe,
    universe_wide_sector_match,
    verify_inverse_signals,
)
from app.services.universe import nightly_universe_refresh

logger = logging.getLogger(__name__)

SYNC_SEMAPHORE = asyncio.Semaphore(3)

scheduler = AsyncIOScheduler()


async def _sync_single_stock(stock: Stock) -> dict:
    """종목 하나를 별도 세션으로 동기화한다 (병렬 안전)."""
    async with SYNC_SEMAPHORE:
        async with async_session() as db:
            results = {}
            try:
                prices = await sync_prices(db, stock)
                financials = await sync_financials(db, stock)
                news = await sync_news(db, stock)
                disclosures = await sync_disclosures(db, stock)

                results = {
                    "ticker": stock.ticker,
                    "prices": prices.get("prices_synced", 0),
                    "financials": financials.get("financials_synced", 0),
                    "news": news.get("news_synced", 0),
                    "disclosures": disclosures.get("disclosures_synced", 0),
                    "analysis": False,
                }

                # LLM 분석
                if settings.llm_api_key:
                    adapter = get_adapter()
                    analysis = await analyze_stock(db, stock, adapter)
                    results["analysis"] = analysis.get("analysis_created", False)

                errors = []
                for r in [prices, financials, news, disclosures]:
                    if "error" in r:
                        errors.append(r["error"])
                results["errors"] = errors

            except Exception as e:
                logger.error("Sync failed for %s: %s", stock.ticker, e)
                results = {"ticker": stock.ticker, "errors": [str(e)]}

            return results


async def cleanup_old_news_content():
    """오래된 뉴스의 본문(content)을 NULL 처리하여 DB 용량을 관리한다."""
    cutoff = date.today() - timedelta(days=settings.news_content_retention_days)
    async with async_session() as db:
        result = await db.execute(
            update(News)
            .where(News.published_at < cutoff, News.content.isnot(None))
            .values(content=None)
        )
        await db.commit()
        cleaned = result.rowcount
        if cleaned > 0:
            logger.info("Cleaned content from %d old news articles (before %s)", cleaned, cutoff)
        return {"cleaned": cleaned}


async def scheduled_sync_job():
    """스케줄러가 호출하는 전체 동기화 잡."""
    logger.info("Scheduled sync started")

    async with async_session() as db:
        # 모든 사용자의 즐겨찾기 종목 합집합
        fav_result = await db.execute(
            select(Stock).join(Favorite, Favorite.stock_id == Stock.id).distinct()
        )
        stocks = fav_result.scalars().all()

    if not stocks:
        logger.info("No favorited stocks to sync")
        return

    # 병렬 실행 (각 종목 별도 세션, Semaphore(3) 제한)
    tasks = [_sync_single_stock(stock) for stock in stocks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 환율 동기화 (별도 세션)
    async with async_session() as db:
        await sync_exchange_rates(db)

    # 오래된 뉴스 본문 정리
    await cleanup_old_news_content()

    synced = [r["ticker"] for r in results if isinstance(r, dict) and "ticker" in r]
    logger.info("Scheduled sync completed: %d stocks synced (%s)", len(synced), ", ".join(synced))


async def run_kr_analysis_batch() -> None:
    """v2 KR market batch — analyze unique KR favorites with cost guard."""
    if not can_proceed():
        logger.warning("kr v2 batch skipped: daily budget exceeded")
        return
    tickers = await unique_favorite_tickers(markets=["KRX", "KOSPI", "KOSDAQ"])
    logger.info("kr v2 batch: %d unique tickers", len(tickers))
    for t in tickers:
        if not can_proceed():
            logger.warning("kr v2 batch halted at %s: budget exceeded", t)
            break
        try:
            await analyze(t)
        except Exception:
            logger.exception("kr v2 batch analyze failed for %s", t)


async def run_sec_8k_extraction() -> None:
    """Nightly SEC 8-K Item 1.01 extraction over the US Tier 1+2 universe.

    Conservative defaults — `limit=50` cap + `sleep=0.5s` SEC pacing. Density
    measured at backfill: ~2.5 contract rows / 30 ticker / week. Daily run with
    a 2-day window means each filing is seen ~twice (idempotent ON CONFLICT).

    P1.6 v2 — plan §12 v2 step.
    """
    from app.services.analyst.cost import can_proceed

    if not can_proceed():
        logger.warning("sec_8k extraction skipped: daily LLM budget exceeded")
        return

    since = date.today() - timedelta(days=2)
    try:
        summaries = await extract_sec_contracts_for_universe(
            since=since, limit=50, sleep_between=0.5
        )
    except Exception as e:  # noqa: BLE001 — never crash the scheduler loop
        logger.exception("sec_8k extraction failed: %s", e)
        return

    filings = sum(s.get("filings_seen", 0) for s in summaries)
    upserted = sum(s.get("upserted", 0) for s in summaries)
    buffered = sum(s.get("buffered", 0) for s in summaries)
    logger.info(
        "sec_8k nightly: tickers=%d filings=%d upserted=%d buffered=%d",
        len(summaries), filings, upserted, buffered,
    )


async def run_news_extraction() -> None:
    """Nightly news LLM RAG over Tier 1+2 universe (P1.6 v3).

    Conservative: limit=50 ticker, 5 articles each, 7-day window. Filters
    null-content articles. Cost gate via `can_proceed()`.
    """
    from app.services.analyst.cost import can_proceed

    if not can_proceed():
        logger.warning("news extraction skipped: daily LLM budget exceeded")
        return

    since = date.today() - timedelta(days=7)
    try:
        summaries = await extract_news_relations_for_universe(
            since=since, limit=50, articles_per_run=5, sleep_between=0.3
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("news extraction failed: %s", e)
        return

    articles = sum(s.get("articles_seen", 0) for s in summaries)
    upserted = sum(s.get("upserted", 0) for s in summaries)
    buffered = sum(s.get("buffered", 0) for s in summaries)
    logger.info(
        "news nightly: tickers=%d articles=%d upserted=%d buffered=%d",
        len(summaries), articles, upserted, buffered,
    )


async def run_inverse_verification() -> None:
    """Nightly price-correlation check on inverse-signal relations (P1.6 v3).

    DB-only (no LLM cost). Boosts confidence when actual price corr confirms
    LLM-inferred inverse, penalises when it contradicts. Idempotent up to
    bounded confidence drift per night.
    """
    try:
        summary = await verify_inverse_signals()
    except Exception as e:  # noqa: BLE001
        logger.exception("inverse verification failed: %s", e)
        return
    logger.info("inverse_verification nightly: %s", summary)


async def run_us_analysis_batch() -> None:
    """v2 US market batch — analyze unique US favorites with cost guard."""
    if not can_proceed():
        logger.warning("us v2 batch skipped: daily budget exceeded")
        return
    tickers = await unique_favorite_tickers(markets=["NASDAQ", "NYSE", "AMEX"])
    logger.info("us v2 batch: %d unique tickers", len(tickers))
    for t in tickers:
        if not can_proceed():
            logger.warning("us v2 batch halted at %s: budget exceeded", t)
            break
        try:
            await analyze(t)
        except Exception:
            logger.exception("us v2 batch analyze failed for %s", t)


def init_scheduler():
    """스케줄러를 초기화하고 잡을 등록한다."""
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled")
        return

    tz = ZoneInfo(settings.scheduler_timezone)

    # Phase A keyword sync (legacy, still active)
    morning_h, morning_m = map(int, settings.scheduler_morning.split(":"))
    evening_h, evening_m = map(int, settings.scheduler_evening.split(":"))

    scheduler.add_job(
        scheduled_sync_job,
        CronTrigger(hour=morning_h, minute=morning_m, timezone=tz),
        id="morning_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_sync_job,
        CronTrigger(hour=evening_h, minute=evening_m, timezone=tz),
        id="evening_sync",
        replace_existing=True,
    )

    # v2 KR/US split — cron strings configured in .env
    scheduler.add_job(
        run_kr_analysis_batch,
        CronTrigger.from_crontab(settings.schedule_kr_morning, timezone=tz),
        id="v2_kr_morning",
        replace_existing=True,
    )
    scheduler.add_job(
        run_kr_analysis_batch,
        CronTrigger.from_crontab(settings.schedule_kr_afternoon, timezone=tz),
        id="v2_kr_afternoon",
        replace_existing=True,
    )
    scheduler.add_job(
        run_us_analysis_batch,
        CronTrigger.from_crontab(settings.schedule_us_evening, timezone=tz),
        id="v2_us_evening",
        replace_existing=True,
    )
    scheduler.add_job(
        run_us_analysis_batch,
        CronTrigger.from_crontab(settings.schedule_us_night, timezone=tz),
        id="v2_us_night",
        replace_existing=True,
    )

    # P1.7 Phase B: nightly reference universe refresh.
    # KR 시장 open 전 06:00 KST. S&P 500 wikipedia fetch는 비용 0이라 매일 같이 실행.
    scheduler.add_job(
        nightly_universe_refresh,
        CronTrigger(hour=6, minute=0, timezone=tz),
        id="universe_refresh_daily",
        replace_existing=True,
    )

    # P1.6 v0: universe-wide sector cross-match. Runs 30 min after the
    # universe refresh so freshly-promoted Tier 1 entrants are picked up.
    scheduler.add_job(
        universe_wide_sector_match,
        CronTrigger(hour=6, minute=30, timezone=tz),
        id="ontology_sector_match_daily",
        replace_existing=True,
    )

    # P1.6 v2: SEC 8-K Item 1.01 extraction (LLM RAG).
    # 06:45 KST = 17:45 ET previous day — captures all of the US trading-day's
    # post-market 8-K filings with a 2-day rolling window for idempotency.
    scheduler.add_job(
        run_sec_8k_extraction,
        CronTrigger(hour=6, minute=45, timezone=tz),
        id="ontology_sec_8k_daily",
        replace_existing=True,
    )

    # P1.6 v3: News-driven competitor / inverse-signal extraction (LLM RAG).
    scheduler.add_job(
        run_news_extraction,
        CronTrigger(hour=6, minute=50, timezone=tz),
        id="ontology_news_daily",
        replace_existing=True,
    )

    # P1.6 v3: Price correlation verification of inverse signals (DB-only).
    # Runs after news extraction so freshly-extracted rows are also verified.
    scheduler.add_job(
        run_inverse_verification,
        CronTrigger(hour=7, minute=0, timezone=tz),
        id="ontology_inverse_verify_daily",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: phase A %s/%s + v2 KR %s,%s + v2 US %s,%s "
        "+ universe refresh 06:00 + sector_match 06:30 + sec_8k 06:45 "
        "+ news 06:50 + inverse_verify 07:00 (%s)",
        settings.scheduler_morning,
        settings.scheduler_evening,
        settings.schedule_kr_morning,
        settings.schedule_kr_afternoon,
        settings.schedule_us_evening,
        settings.schedule_us_night,
        settings.scheduler_timezone,
    )
