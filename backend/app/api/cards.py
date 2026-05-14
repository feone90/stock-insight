"""v2 card endpoints: GET card / POST analyze / POST refresh (with cooldown).

가족 dev 환경 self-heal:
  - `is_analyzable` fail 사유가 'no price history'면 즉시 sync_prices 호출.
  - analyzable 이라도 Financial row 없거나 News 가 5건 미만이면 보강 sync.
  - analyze 트리거 시 ontology news extraction 도 같이 background 실행.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.disclosure import sync_disclosures
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.stock_price import sync_prices
from app.config import settings
from app.database import async_session, get_db
from app.dependencies import get_stock_or_404
from app.models import News, Stock
from app.models.analysis import Analysis
from app.models.financial import Financial
from app.services.analyst.cost import can_proceed
from app.services.analyst.engine import analyze, is_analyzable
from app.services.ontology import extract_news_relations_for_ticker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["cards"])

# In-memory per-ticker cooldown tracker.
_last_refresh: dict[str, float] = {}


_MIN_NEWS_FOR_ANALYZE = 5


async def _ensure_analyzable(
    ticker: str, stock: Stock, db: AsyncSession
) -> tuple[bool, str | None]:
    """`is_analyzable` 체크 + 데이터 stale 여부 검사.

    self-heal 트리거 조건:
      1. is_analyzable fail (no price history / current_price <= 0)
      2. Financial row 없음 (PER/PBR/매출 비어있는 카드 방지)
      3. News 5건 미만 (한 줄 요약이라도 LLM 이 만들 만한 input 보장)

    handler 의 `db` 세션을 그대로 재사용해야 stock object detach 안 됨.
    """
    ok, reason = await is_analyzable(ticker)

    needs_sync = False
    sync_reason = reason
    if not ok and reason in ("no price history", "current_price <= 0"):
        needs_sync = True
    elif ok:
        fin_count = (
            await db.execute(
                select(func.count()).select_from(Financial).where(
                    Financial.stock_id == stock.id
                )
            )
        ).scalar() or 0
        news_count = (
            await db.execute(
                select(func.count()).select_from(News).where(
                    News.stock_id == stock.id
                )
            )
        ).scalar() or 0
        if fin_count == 0 or news_count < _MIN_NEWS_FOR_ANALYZE:
            needs_sync = True
            sync_reason = f"stale (fin={fin_count} news={news_count})"

    if needs_sync:
        logger.info("self-heal sync for %s (reason=%s)", ticker, sync_reason)
        try:
            await sync_prices(db, stock)
            await sync_news(db, stock)
            await sync_financials(db, stock)
            await sync_disclosures(db, stock)
        except Exception as e:  # noqa: BLE001
            logger.exception("self-heal failed for %s: %s", ticker, e)
            return False, f"self-heal failed: {e}"
        ok, reason = await is_analyzable(ticker)
    return ok, reason


async def _extract_relations_safe(ticker: str) -> None:
    """analyze 와 같이 background 에서 도는 ontology 추출. budget/실패는 swallow.

    가족 환경 — 새로 본 종목이면 analyze 직후 supply-chain/competitor 관계도
    당일치 뉴스에서 한 번 채워줘야 사용자가 카드 다시 안 열어도 됨.

    Window 는 admin force-extract 와 동일한 14일 / 10 articles. 짧은 윈도우
    (7일/5건) 로는 mid-cap KR 종목에서 LLM 이 충분한 entity context 못 받아
    관계 0건 반환하는 케이스가 다수 (240810 원익IPS, 042700 한미반도체 검증됨).
    """
    if not can_proceed():
        logger.info("ontology extract skipped for %s: budget", ticker)
        return
    try:
        summary = await extract_news_relations_for_ticker(
            ticker,
            since=date.today() - timedelta(days=14),
            articles_per_run=10,
        )
        logger.info(
            "ontology extract %s: seen=%s short=%s llm=%s upserted=%s buffered=%s",
            ticker,
            summary.get("articles_seen"),
            summary.get("articles_skipped_short"),
            summary.get("llm_relations_returned"),
            summary.get("upserted"),
            summary.get("buffered"),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("ontology extract failed for %s: %s", ticker, e)


@router.get("/{ticker}/card")
async def get_card(
    ticker: str,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Analysis)
            .where(
                Analysis.stock_id == stock.id,
                Analysis.schema_version == "v2",
            )
            .order_by(Analysis.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not row or not row.card_data:
        raise HTTPException(
            status_code=404,
            detail=f"v2 card for {ticker.upper()} not yet generated. POST /analyze first.",
        )
    return row.card_data


@router.post("/{ticker}/analyze", status_code=202)
async def trigger_analyze(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")
    ok, reason = await _ensure_analyzable(ticker, stock, db)
    if not ok:
        raise HTTPException(422, f"not analyzable: {reason}")
    bg.add_task(analyze, ticker)
    bg.add_task(_extract_relations_safe, ticker)
    return {"status": "queued", "ticker": ticker.upper()}


_last_data_refresh: dict[str, float] = {}
_DATA_REFRESH_COOLDOWN_S = 60  # 1분 — 외부 API rate limit 보호. AI 의견 다시 의
# 300s(5분)보다 가볍게 — LLM cost 0 이라 더 자주 가능.


@router.post("/{ticker}/data_refresh", status_code=202)
async def data_refresh(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    """LLM 0 — underlying 데이터만 동기화 (price/news/financials/disclosures).

    2026-05-14 사용자 통찰: "실시간값이랑 새로 추가된 뉴스가 있으면 그정도
    + 의견변경 정도 말고는 없지않나". `/refresh` 는 LLM 2-stage 파이프라인
    풀로 다시 돌아 $0.25 → cost 낭비. 데이터만 새로 받고 AI 의견은 기존
    유지가 가족 dev 비용 효율.

    효과:
    - 차트·가격: 별도 GET /prices · /stocks/{ticker} endpoint 가 매번 fresh
      DB query → 이 endpoint 호출 후 즉시 새 가격 노출.
    - 카드 내 펀더멘털/수급/관계/실적·분석가 등: card_data JSON 에 박혀
      있어 이 endpoint 로는 안 바뀜. AI 의견 다시 (`/refresh`) 클릭 시
      그 시점에 새 data + new LLM narrative 로 풀 rebuild.

    1분 cooldown — 외부 API rate limit 보호.
    """
    key = ticker.upper()
    now = time.monotonic()
    last = _last_data_refresh.get(key, 0.0)
    if now - last < _DATA_REFRESH_COOLDOWN_S:
        remaining = int(_DATA_REFRESH_COOLDOWN_S - (now - last))
        raise HTTPException(429, f"cooldown: try again in {remaining}s")
    _last_data_refresh[key] = now

    async def _sync_underlying() -> None:
        async with async_session() as own_db:
            from app.models import Stock as _Stock
            fresh = (
                await own_db.execute(
                    select(_Stock).where(_Stock.ticker == ticker)
                )
            ).scalar_one_or_none()
            if not fresh:
                return
            for fn in (sync_prices, sync_news, sync_financials, sync_disclosures):
                try:
                    await fn(own_db, fresh)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "data_refresh %s collector %s failed: %s",
                        ticker, fn.__name__, e,
                    )

    bg.add_task(_sync_underlying)
    return {"status": "data_refresh_queued", "ticker": key}


@router.post("/{ticker}/refresh", status_code=202)
async def force_refresh(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")

    key = ticker.upper()
    now = time.monotonic()
    last = _last_refresh.get(key, 0.0)
    if now - last < settings.analysis_cooldown_seconds:
        remaining = int(settings.analysis_cooldown_seconds - (now - last))
        raise HTTPException(429, f"cooldown: try again in {remaining}s")
    ok, reason = await _ensure_analyzable(ticker, stock, db)
    if not ok:
        raise HTTPException(422, f"not analyzable: {reason}")
    _last_refresh[key] = now
    bg.add_task(analyze, ticker)
    bg.add_task(_extract_relations_safe, ticker)
    return {"status": "refresh_queued", "ticker": key}
