"""v2 card endpoints: GET card / POST analyze / POST refresh (with cooldown).

가족 dev 환경 self-heal:
  - `is_analyzable` fail 사유가 'no price history'면 즉시 sync_prices를
    1회 호출 후 재체크. 사용자는 admin endpoint 의식할 필요 없음.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.disclosure import sync_disclosures
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.stock_price import sync_prices
from app.config import settings
from app.database import async_session, get_db
from app.dependencies import get_stock_or_404
from app.models import Stock
from app.models.analysis import Analysis
from app.services.analyst.cost import can_proceed
from app.services.analyst.engine import analyze, is_analyzable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["cards"])

# In-memory per-ticker cooldown tracker.
_last_refresh: dict[str, float] = {}


async def _ensure_analyzable(
    ticker: str, stock: Stock, db: AsyncSession
) -> tuple[bool, str | None]:
    """`is_analyzable` 체크. fail 사유가 'no price history' 또는
    'current_price <= 0'이면 sync_prices 1회 호출 후 재체크 (self-heal).

    sync_prices는 handler가 넘긴 `db` 세션을 그대로 재사용해야 stock object
    가 detach되지 않음. exception은 graceful 처리.

    Returns (ok, reason). 자가 치유 후에도 fail이면 reason 반환.
    """
    ok, reason = await is_analyzable(ticker)
    if ok:
        return True, None
    if reason in ("no price history", "current_price <= 0"):
        logger.info("self-heal: syncing all collectors for %s (reason=%s)", ticker, reason)
        # 4 collector를 한 번에 호출 — 모두 idempotent. collector는 외부 API
        # 실패 시 dict에 'error' 필드만 담아 반환하므로 exception 거의 없음.
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
    return {"status": "queued", "ticker": ticker.upper()}


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
    return {"status": "refresh_queued", "ticker": key}
