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

    jobs = {
        "fred": run_fred_macro_sync,
        "sector_match": universe_wide_sector_match,
        "news_extraction": run_news_extraction,
        "sec_8k": run_sec_8k_extraction,
        "inverse_verify": run_inverse_verification,
        "universe_refresh": nightly_universe_refresh,
        "sync_favorites": scheduled_sync_job,
    }
    if job_id not in jobs:
        raise HTTPException(
            status_code=404,
            detail=f"unknown job_id '{job_id}'. Available: {sorted(jobs.keys())}",
        )
    try:
        await jobs[job_id]()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"job '{job_id}' failed: {e}")
    return {"status": "ok", "job": job_id}
