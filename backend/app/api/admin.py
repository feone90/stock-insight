from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserInfo, require_admin
from app.config import settings
from app.database import get_db
from app.dependencies import get_stock_or_404
from app.models import Favorite, Stock
from app.schemas.stock import SyncAllResult, SyncGlobalResult, SyncResult
from app.collectors.stock_price import sync_prices
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.disclosure import sync_disclosures
from app.collectors.exchange_rate import sync_exchange_rates
from app.services.llm.adapter import get_adapter
from app.services.llm.analyzer import analyze_stock

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/sync/stock/{ticker}", response_model=SyncResult)
async def sync_stock(stock: Stock = Depends(get_stock_or_404), db: AsyncSession = Depends(get_db), _admin: UserInfo = Depends(require_admin)):

    prices_result = await sync_prices(db, stock)
    financials_result = await sync_financials(db, stock)
    news_result = await sync_news(db, stock)
    disclosures_result = await sync_disclosures(db, stock)

    # LLM 분석 (API 키가 설정된 경우만)
    analysis_result = {"analysis_created": False}
    if settings.llm_api_key:
        adapter = get_adapter()
        analysis_result = await analyze_stock(db, stock, adapter)

    errors = []
    for r in [prices_result, financials_result, news_result, disclosures_result, analysis_result]:
        if "error" in r:
            errors.append(r["error"])

    return {
        "status": "ok",
        "ticker": stock.ticker,
        "synced": {
            "prices": prices_result.get("prices_synced", 0),
            "financials": financials_result.get("financials_synced", 0),
            "news": news_result.get("news_synced", 0),
            "disclosures": disclosures_result.get("disclosures_synced", 0),
            "analysis": analysis_result.get("analysis_created", False),
        },
        "financials_detail": {
            k: financials_result.get(k)
            for k in ("source", "period", "per", "pbr", "roe", "market_cap", "revenue", "net_income")
        },
        "errors": errors,
    }


@router.post("/sync/global", response_model=SyncGlobalResult)
async def sync_global(db: AsyncSession = Depends(get_db), _admin: UserInfo = Depends(require_admin)):
    rates_result = await sync_exchange_rates(db)

    errors = []
    if "error" in rates_result:
        errors.append(rates_result["error"])

    return {
        "status": "ok",
        "synced": {
            "exchange_rates": rates_result.get("exchange_rates_synced", 0),
        },
        "errors": errors,
    }


@router.post("/sync/all", response_model=SyncAllResult)
async def sync_all(db: AsyncSession = Depends(get_db), _admin: UserInfo = Depends(require_admin)):
    # 모든 사용자의 즐겨찾기 종목 합집합 (중복 제거)
    fav_result = await db.execute(
        select(Stock).join(Favorite, Favorite.stock_id == Stock.id).distinct()
    )
    stocks = fav_result.scalars().all()

    total = {"prices": 0, "financials": 0, "news": 0, "disclosures": 0, "exchange_rates": 0, "analyses": 0}
    errors = []
    tickers_synced = []

    # LLM 어댑터 (키 설정 시 한 번만 생성)
    adapter = get_adapter() if settings.llm_api_key else None

    for stock in stocks:
        tickers_synced.append(stock.ticker)

        prices_result = await sync_prices(db, stock)
        financials_result = await sync_financials(db, stock)
        news_result = await sync_news(db, stock)
        disclosures_result = await sync_disclosures(db, stock)

        # LLM 분석
        analysis_result = {"analysis_created": False}
        if adapter:
            analysis_result = await analyze_stock(db, stock, adapter)

        total["prices"] += prices_result.get("prices_synced", 0)
        total["financials"] += financials_result.get("financials_synced", 0)
        total["news"] += news_result.get("news_synced", 0)
        total["disclosures"] += disclosures_result.get("disclosures_synced", 0)
        if analysis_result.get("analysis_created"):
            total["analyses"] += 1

        for r in [prices_result, financials_result, news_result, disclosures_result, analysis_result]:
            if "error" in r:
                errors.append(f"[{stock.ticker}] {r['error']}")

    rates_result = await sync_exchange_rates(db)
    total["exchange_rates"] = rates_result.get("exchange_rates_synced", 0)
    if "error" in rates_result:
        errors.append(rates_result["error"])

    return {
        "status": "ok",
        "stocks_synced": tickers_synced,
        "global_synced": True,
        "total_synced": total,
        "errors": errors,
    }


@router.post("/jobs/run/{job_id}")
async def run_job(job_id: str, _admin: UserInfo = Depends(require_admin)):
    """스케줄러의 cron 잡을 수동으로 즉시 실행. 첫 deploy 직후 cron 한 번도
    안 돈 상태에서 데이터 채우기 용도. 잡은 idempotent — 반복 호출 안전.

    Available job_id:
      - fred                : FRED 매크로 (VIX/US10Y/FedFunds/실업률) snapshot
      - sector_match        : universe-wide KSIC→GICS sector_match
      - news_extraction     : 뉴스 LLM RAG competitor/inverse 추출
      - sec_8k              : SEC 8-K Item 1.01 contract 추출
      - inverse_verify      : inverse signal 가격 상관관계 검증
      - universe_refresh    : reference universe (KOSPI + S&P 500) refresh
      - sync_favorites      : 즐겨찾기 종목 가격/재무/뉴스/공시 동기화
    """
    from app.scheduler import (
        run_fred_macro_sync,
        run_inverse_verification,
        run_news_extraction,
        run_sec_8k_extraction,
        scheduled_sync_job,
    )
    from app.services.ontology import universe_wide_sector_match
    from app.services.universe import nightly_universe_refresh

    from app.collectors.truth_social import sync_truth_social
    from app.database import async_session as _async_session
    from app.services.political.analyzer import analyze_pending_signals

    async def _truth_social_job():
        async with _async_session() as db:
            return await sync_truth_social(db)

    async def _political_analyze_job():
        async with _async_session() as db:
            return await analyze_pending_signals(db)

    jobs = {
        "fred": run_fred_macro_sync,
        "sector_match": universe_wide_sector_match,
        "news_extraction": run_news_extraction,
        "sec_8k": run_sec_8k_extraction,
        "inverse_verify": run_inverse_verification,
        "universe_refresh": nightly_universe_refresh,
        "sync_favorites": scheduled_sync_job,
        "truth_social": _truth_social_job,
        "political_analyze": _political_analyze_job,
    }
    if job_id not in jobs:
        raise HTTPException(
            status_code=404,
            detail=f"unknown job_id '{job_id}'. Available: {sorted(jobs.keys())}",
        )
    try:
        result = await jobs[job_id]()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"job '{job_id}' failed: {e}")
    # job 함수가 dict 반환 시 그대로 노출 (None인 경우 빈 dict). 검증/디버깅용.
    return {"status": "ok", "job": job_id, "result": result if result is not None else {}}


@router.post("/extract_relations/{ticker}")
async def extract_relations_for_one(
    ticker: str, _admin: UserInfo = Depends(require_admin)
):
    """한 ticker에 대해 LLM news relation extraction 강제 실행 + 결과 dict 반환.

    universe-wide news_extraction 잡이 빈 result 만 보여줘서 진단이 어렵기 때문에
    per-ticker 진입점을 따로 둔다. articles_seen/upserted/buffered + (있다면)
    LLM 이 만든 first relation 예시를 노출.
    """
    from datetime import date, timedelta
    from app.services.ontology import extract_news_relations_for_ticker

    try:
        summary = await extract_news_relations_for_ticker(
            ticker, since=date.today() - timedelta(days=14), articles_per_run=10
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=f"extract failed: {e}")
    return {"status": "ok", "ticker": ticker, "summary": summary}


@router.get("/inspect/relations/{ticker}")
async def inspect_relations(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """ticker의 outgoing StockRelation row 5건의 raw extra_metadata 노출.

    rationale 데이터 흐름 진단용 — LLM extract → validator → DB → data_layer.
    """
    from app.models.relation import StockRelation

    stock = (
        await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    ).scalar_one_or_none()
    if not stock:
        raise HTTPException(404, detail=f"ticker '{ticker}' not in DB")
    rows = (
        await db.execute(
            select(StockRelation)
            .where(StockRelation.from_stock_id == stock.id)
            .order_by(StockRelation.refreshed_at.desc().nulls_last())
            .limit(10)
        )
    ).scalars().all()
    return {
        "ticker": ticker.upper(),
        "stock_id": stock.id,
        "rows": [
            {
                "to_target": r.to_target,
                "relation_type": r.relation_type,
                "source": r.source,
                "confidence": r.confidence,
                "refreshed_at": r.refreshed_at.isoformat() if r.refreshed_at else None,
                "extra_metadata": r.extra_metadata,
            }
            for r in rows
        ],
    }


@router.get("/inspect/news/{ticker}")
async def inspect_news(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """ticker의 최근 뉴스 본문 길이 분포 + 샘플 5건. 본문 scraping 확인용."""
    from sqlalchemy import func
    from app.models.news import News

    stock = (
        await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    ).scalar_one_or_none()
    if not stock:
        raise HTTPException(404, detail=f"ticker '{ticker}' not in DB")
    total = (
        await db.execute(
            select(func.count()).select_from(News).where(News.stock_id == stock.id)
        )
    ).scalar() or 0
    long_count = (
        await db.execute(
            select(func.count()).select_from(News).where(
                News.stock_id == stock.id,
                func.length(News.content) >= 200,
            )
        )
    ).scalar() or 0
    samples = (
        await db.execute(
            select(News.title, News.source, News.url, func.length(News.content).label("len"))
            .where(News.stock_id == stock.id)
            .order_by(News.published_at.desc())
            .limit(5)
        )
    ).all()
    return {
        "ticker": ticker.upper(),
        "stock_id": stock.id,
        "total_news": total,
        "with_long_body": long_count,
        "samples": [
            {"title": s.title, "source": s.source, "url": s.url, "content_len": s.len}
            for s in samples
        ],
    }


@router.post("/political/seed_sample")
async def seed_political_sample(
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """Demo/검증용 — 실제 트럼프 매크로 발언 sample 5개 seed.

    trumpstruth.org/feed의 RT 다수로 substantive content 부족 + pagination
    제한이라 historical backfill 어려움. demo + UI 검증을 위해 매크로
    영향 명확한 sample 5개를 직접 insert. analyzer가 ticker 매핑.

    실제 트럼프가 최근 1년 사이 했던 발언의 paraphrase. demo source 명시
    (source='sample_macro'). 운영 시점에는 매시 cron이 자연 축적.
    """
    from datetime import datetime, timedelta
    from app.models.political_signal import PoliticalSignal

    samples = [
        {
            "id": "sample_tariff_china_2026_05_10",
            "posted_at": datetime.utcnow() - timedelta(days=2),
            "content": (
                "China is going to pay a 60% TARIFF on ALL goods coming into our "
                "Country. This will protect American Semiconductor, Auto, and Steel "
                "industries. Make America Great Again!"
            ),
            "url": "https://example.com/sample/tariff",
        },
        {
            "id": "sample_ai_infra_2026_05_09",
            "posted_at": datetime.utcnow() - timedelta(days=3),
            "content": (
                "MASSIVE new AI infrastructure deal — $500 BILLION investment in "
                "American semiconductors and data centers. NVIDIA, AMD will benefit "
                "tremendously. This is the future!"
            ),
            "url": "https://example.com/sample/ai",
        },
        {
            "id": "sample_iran_sanctions_2026_05_08",
            "posted_at": datetime.utcnow() - timedelta(days=4),
            "content": (
                "Iran will face the toughest SANCTIONS ever. Oil prices will surge. "
                "We will not allow them to have nuclear weapons. American energy "
                "independence FIRST!"
            ),
            "url": "https://example.com/sample/iran",
        },
        {
            "id": "sample_fed_rate_2026_05_07",
            "posted_at": datetime.utcnow() - timedelta(days=5),
            "content": (
                "The Federal Reserve must CUT rates immediately. The economy is "
                "STRONG but high rates are hurting American businesses and homeowners. "
                "We need lower rates NOW!"
            ),
            "url": "https://example.com/sample/fed",
        },
        {
            "id": "sample_korea_chip_2026_05_06",
            "posted_at": datetime.utcnow() - timedelta(days=6),
            "content": (
                "South Korea is taking advantage of our trade deals. We will impose "
                "TARIFFS on Korean semiconductor and auto imports. Samsung, Hyundai "
                "must build factories in America!"
            ),
            "url": "https://example.com/sample/korea",
        },
    ]

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    inserted = 0
    for s in samples:
        stmt = (
            pg_insert(PoliticalSignal)
            .values(
                source="sample_macro",
                source_post_id=s["id"],
                author="realDonaldTrump",
                posted_at=s["posted_at"],
                content=s["content"],
                content_lang="en",
                url=s["url"],
            )
            .on_conflict_do_nothing(
                index_elements=["source", "source_post_id"],
            )
        )
        result = await db.execute(stmt)
        if result.rowcount and result.rowcount > 0:
            inserted += 1
    await db.commit()
    return {
        "status": "ok",
        "inserted": inserted,
        "total_samples": len(samples),
        "next_step": "POST /api/admin/jobs/run/political_analyze",
    }


@router.get("/political/status")
async def political_status(
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """정치 시그널 DB 상태 확인 (검증/디버깅용)."""
    from app.models.political_signal import PoliticalSignal, PoliticalSignalTicker
    from sqlalchemy import func as sql_func

    total = (
        await db.execute(select(sql_func.count()).select_from(PoliticalSignal))
    ).scalar() or 0
    analyzed = (
        await db.execute(
            select(sql_func.count())
            .select_from(PoliticalSignal)
            .where(PoliticalSignal.analyzed_at.isnot(None))
        )
    ).scalar() or 0
    relevant = (
        await db.execute(
            select(sql_func.count())
            .select_from(PoliticalSignal)
            .where(PoliticalSignal.is_market_relevant.is_(True))
        )
    ).scalar() or 0
    ticker_rows = (
        await db.execute(select(sql_func.count()).select_from(PoliticalSignalTicker))
    ).scalar() or 0
    latest = (
        await db.execute(
            select(PoliticalSignal)
            .order_by(PoliticalSignal.posted_at.desc())
            .limit(3)
        )
    ).scalars().all()
    # substantive = RT 아닌 본인 발언. 진짜 분석 대상.
    substantive = (
        await db.execute(
            select(PoliticalSignal)
            .where(~PoliticalSignal.content.like("RT:%"))
            .order_by(PoliticalSignal.posted_at.desc())
            .limit(5)
        )
    ).scalars().all()

    def _serialize(s):
        return {
            "posted_at": s.posted_at.isoformat() if s.posted_at else None,
            "content_preview": (s.content or "")[:300],
            "analyzed": s.analyzed_at is not None,
            "is_relevant": s.is_market_relevant,
            "summary_ko": s.summary_ko,
            "sentiment": s.overall_sentiment,
            "macro_themes": s.macro_themes,
            "url": s.url,
        }

    return {
        "total_signals": total,
        "analyzed": analyzed,
        "market_relevant": relevant,
        "ticker_impacts": ticker_rows,
        "latest_3": [_serialize(s) for s in latest],
        "substantive_5": [_serialize(s) for s in substantive],
    }
