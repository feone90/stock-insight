"""Unique-ticker selection across all users' favorites.

Used by the KR/US scheduler to dedup so 4 family members favoriting the same
stock = 1 analysis.
"""
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session
from app.models import Analysis, Favorite, Stock

_MIN_DT = datetime.min.replace(tzinfo=timezone.utc)


def _parse_generated_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


async def unique_favorite_tickers(
    markets: list[str] | None = None,
) -> list[str]:
    """Distinct tickers across ALL users' favorites, stale cards first.

    The scheduler has a daily LLM budget cap. If we process favorites in DB's
    arbitrary distinct order, expensive fresh cards can consume the budget
    while old cards stay stale for days. Sorting by latest v2 card timestamp
    means missing/old cards are refreshed first, and fresh cards naturally move
    to the back of the next run.
    """
    async with async_session() as db:
        stmt = (
            select(Stock.id, Stock.ticker)
            .join(Favorite, Favorite.stock_id == Stock.id)
            .distinct()
        )
        if markets:
            stmt = stmt.where(Stock.market.in_(markets))
        stock_rows = (await db.execute(stmt)).all()

        stock_ids = [row[0] for row in stock_rows]
        latest_by_stock_id: dict[int, datetime] = {}
        if stock_ids:
            analysis_rows = (
                await db.execute(
                    select(Analysis.stock_id, Analysis.card_data)
                    .where(
                        Analysis.stock_id.in_(stock_ids),
                        Analysis.schema_version == "v2",
                        Analysis.card_data.isnot(None),
                    )
                )
            ).all()
            for stock_id, card_data in analysis_rows:
                if not isinstance(card_data, dict):
                    continue
                generated_at = card_data.get("generated_at")
                if not isinstance(generated_at, str) or not generated_at:
                    continue
                parsed = _parse_generated_at(generated_at)
                if parsed is None:
                    continue
                prev = latest_by_stock_id.get(stock_id)
                if prev is None or parsed > prev:
                    latest_by_stock_id[stock_id] = parsed

    ordered = sorted(
        stock_rows,
        key=lambda row: (
            row[0] in latest_by_stock_id,
            latest_by_stock_id.get(row[0], _MIN_DT),
            row[1],
        ),
    )
    return [ticker for _, ticker in ordered]
