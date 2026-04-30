"""Tier 1 bulk upsert helper — shared by seed and nightly refresh.

`bulk_upsert_tier1` is idempotent:
  - tier 3 (latent) row → promoted to tier 1
  - tier 2 (user-touched) row → tier preserved, metadata refreshed
  - tier 1 row → metadata refreshed

Plan: docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md §6, §9
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime, timezone

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session
from app.models.stock import Stock
from app.services.universe.types import UniverseRow

_BATCH_SIZE = 1000
TIER_REFERENCE = 1
TIER_USER_TOUCHED = 2
TIER_LATENT = 3


def dedupe_by_ticker(rows: list[UniverseRow]) -> list[UniverseRow]:
    """Last-write-wins by ticker; the global ticker UNIQUE in `stocks`
    enforces it at DB level too.
    """
    by_ticker: dict[str, UniverseRow] = {}
    for row in rows:
        by_ticker[row.ticker] = row
    return list(by_ticker.values())


async def bulk_upsert_tier1(rows: list[UniverseRow]) -> int:
    """Bulk PG `INSERT ... ON CONFLICT (ticker) DO UPDATE` in 1000-row chunks."""
    if not rows:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    total = 0
    async with async_session() as session:
        for chunk in _chunked(rows, _BATCH_SIZE):
            payload = [
                {
                    "ticker": r.ticker,
                    "name": r.name,
                    "market": r.market,
                    "sector": r.sector,
                    "industry_group": r.industry_group,
                    "tier": TIER_REFERENCE,
                    "universe_source": r.universe_source,
                    "tier_updated_at": now,
                }
                for r in chunk
            ]
            stmt = pg_insert(Stock).values(payload)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker"],
                set_={
                    "name": stmt.excluded.name,
                    "market": stmt.excluded.market,
                    "sector": stmt.excluded.sector,
                    "industry_group": stmt.excluded.industry_group,
                    "universe_source": stmt.excluded.universe_source,
                    "tier": case(
                        (Stock.tier == TIER_LATENT, TIER_REFERENCE),
                        else_=Stock.tier,
                    ),
                    "tier_updated_at": func.now(),
                },
            )
            await session.execute(stmt)
            total += len(payload)
        await session.commit()
    return total


def _chunked(rows: Iterable[UniverseRow], size: int) -> Iterator[list[UniverseRow]]:
    buf: list[UniverseRow] = []
    for r in rows:
        buf.append(r)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
