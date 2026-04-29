"""Production loaders for prewarm.

Kept in a separate module so the adapter layer (`prewarm.py`,
`dartlab_adapter.py`, etc.) stays DB-agnostic at module-import time —
unit tests for the adapters never need a live database.
"""
from __future__ import annotations

from sqlalchemy import desc, func, select

from app.database import async_session
from app.models import Favorite, Stock


async def top_favorited_tickers(limit: int) -> list[str]:
    """Most-favorited tickers across all users, ordered by count desc.

    Used by `app.main.lifespan` to seed the prewarm task.
    """
    async with async_session() as db:
        result = await db.execute(
            select(Stock.ticker)
            .join(Favorite, Favorite.stock_id == Stock.id)
            .group_by(Stock.ticker)
            .order_by(desc(func.count(Favorite.id)))
            .limit(limit)
        )
        return [row[0] for row in result.all()]
