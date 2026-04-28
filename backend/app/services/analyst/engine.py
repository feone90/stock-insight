"""Public entry point for v2 analysis. Glues research + synthesize + persistence.

Persists v2 cards to the existing `analyses` table with `schema_version='v2'`
and the full StockCard JSON in `card_data`. Phase A v1 (keyword) rows coexist.
"""
from __future__ import annotations

import logging
from datetime import date as _date

from sqlalchemy import select

from app.database import async_session
from app.models import Stock
from app.models.analysis import Analysis
from app.schemas.card import StockCard
from app.services.analyst.research import run_research
from app.services.analyst.synthesize import run_synthesize

logger = logging.getLogger(__name__)


async def analyze(ticker: str) -> StockCard:
    """Run full v2 pipeline and persist. Returns the StockCard."""
    ticker = ticker.strip().upper()

    logger.info("analyze[%s]: stage 1 research starting", ticker)
    research = await run_research(ticker)

    logger.info("analyze[%s]: stage 2 synthesize starting", ticker)
    card = await run_synthesize(ticker, research)

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            logger.error("analyze[%s]: stock not found at persistence step", ticker)
            return card

        today = _date.today()
        card_json = card.model_dump(mode="json")
        existing = (
            await db.execute(
                select(Analysis).where(
                    Analysis.stock_id == stock.id,
                    Analysis.date == today,
                    Analysis.period_type == "daily",
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.summary = card.glance.one_line[:500]
            existing.feedback = card.thesis.core_thesis[:1000]
            existing.schema_version = "v2"
            existing.card_data = card_json
            existing.persona_version = card.persona_version
        else:
            db.add(
                Analysis(
                    stock_id=stock.id,
                    date=today,
                    period_type="daily",
                    summary=card.glance.one_line[:500],
                    feedback=card.thesis.core_thesis[:1000],
                    schema_version="v2",
                    card_data=card_json,
                    persona_version=card.persona_version,
                )
            )
        await db.commit()

    logger.info("analyze[%s]: done", ticker)
    return card
