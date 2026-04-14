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
from app.services.llm.adapter import get_adapter
from app.services.llm.analyzer import analyze_stock

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


def init_scheduler():
    """스케줄러를 초기화하고 잡을 등록한다."""
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled")
        return

    tz = ZoneInfo(settings.scheduler_timezone)

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

    scheduler.start()
    logger.info("Scheduler started: %s/%s KST", settings.scheduler_morning, settings.scheduler_evening)
