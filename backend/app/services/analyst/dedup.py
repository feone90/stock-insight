"""Unique-ticker selection across all users' favorites.

Used by the KR/US scheduler to dedup so 4 family members favoriting the same
stock = 1 analysis.
"""
from sqlalchemy import select

from app.database import async_session
from app.models import Favorite, Stock


async def unique_favorite_tickers(
    markets: list[str] | None = None,
) -> list[str]:
    """Distinct tickers across ALL users' favorites, optionally filtered by market."""
    async with async_session() as db:
        stmt = (
            select(Stock.ticker)
            .join(Favorite, Favorite.stock_id == Stock.id)
            .distinct()
        )
        if markets:
            stmt = stmt.where(Stock.market.in_(markets))
        rows = (await db.execute(stmt)).all()
    return [r[0] for r in rows]
