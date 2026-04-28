"""v2 card endpoints: GET card / POST analyze / POST refresh (with cooldown)."""
from __future__ import annotations

import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_stock_or_404
from app.models import Stock
from app.models.analysis import Analysis
from app.services.analyst.cost import can_proceed
from app.services.analyst.engine import analyze, is_analyzable

router = APIRouter(prefix="/api/stocks", tags=["cards"])

# In-memory per-ticker cooldown tracker.
_last_refresh: dict[str, float] = {}


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
):
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")
    ok, reason = await is_analyzable(ticker)
    if not ok:
        raise HTTPException(422, f"not analyzable: {reason}")
    bg.add_task(analyze, ticker)
    return {"status": "queued", "ticker": ticker.upper()}


@router.post("/{ticker}/refresh", status_code=202)
async def force_refresh(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
):
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")

    key = ticker.upper()
    now = time.monotonic()
    last = _last_refresh.get(key, 0.0)
    if now - last < settings.analysis_cooldown_seconds:
        remaining = int(settings.analysis_cooldown_seconds - (now - last))
        raise HTTPException(429, f"cooldown: try again in {remaining}s")
    ok, reason = await is_analyzable(ticker)
    if not ok:
        raise HTTPException(422, f"not analyzable: {reason}")
    _last_refresh[key] = now
    bg.add_task(analyze, ticker)
    return {"status": "refresh_queued", "ticker": key}
