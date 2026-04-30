"""Seed the Tier 1 reference universe (P1.7 Phase A).

Fetches KR (dartlab listing) + US (Wikipedia S&P 500) candidates and
bulk-upserts them as `tier=1` rows. Idempotent — re-runs:

  - tier 3 (latent) rows present in the seed → promoted to tier 1
  - tier 2 (user-touched) rows → tier preserved, metadata refreshed
  - tier 1 rows → metadata refreshed only

Usage::

    uv run python -m scripts.seed_universe          # KR + US (default)
    uv run python -m scripts.seed_universe --kr-only
    uv run python -m scripts.seed_universe --us-only

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §3.1, §5
Plan: docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md §6, §7
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session
from app.models.stock import Stock
from app.services.universe import (
    UniverseRow,
    fetch_kr_universe,
    fetch_us_universe,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 1000
_TIER_REFERENCE = 1
_TIER_USER_TOUCHED = 2
_TIER_LATENT = 3


async def seed_universe(*, include_kr: bool = True, include_us: bool = True) -> dict:
    """Run the seed and return a summary dict for logging / tests."""
    rows: list[UniverseRow] = []
    if include_kr:
        rows.extend(await fetch_kr_universe())
    if include_us:
        rows.extend(await fetch_us_universe())

    if not rows:
        logger.warning("seed_universe: no rows fetched (KR=%s, US=%s)", include_kr, include_us)
        return {"fetched": 0, "upserted": 0}

    deduped = _dedupe_by_ticker(rows)
    upserted = await _bulk_upsert(deduped)
    return {"fetched": len(rows), "deduped": len(deduped), "upserted": upserted}


def _dedupe_by_ticker(rows: list[UniverseRow]) -> list[UniverseRow]:
    """Last-write-wins by ticker. Cross-market collision (e.g. KR/US ticker
    overlap) is rare; the global ticker UNIQUE in `stocks` enforces it.
    """
    by_ticker: dict[str, UniverseRow] = {}
    for row in rows:
        by_ticker[row.ticker] = row
    return list(by_ticker.values())


async def _bulk_upsert(rows: list[UniverseRow]) -> int:
    """PG `INSERT ... ON CONFLICT (ticker) DO UPDATE` with tier preservation.

    `tier` update logic via CASE:
      - latent (tier=3) → promoted to reference (tier=1)
      - user-touched (tier=2) → preserved
      - reference (tier=1) → preserved
    """
    # Stock model uses naive DateTime (matching existing `created_at`); store UTC naive.
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
                    "tier": _TIER_REFERENCE,
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
                        (Stock.tier == _TIER_LATENT, _TIER_REFERENCE),
                        else_=Stock.tier,
                    ),
                    "tier_updated_at": func.now(),
                },
            )
            await session.execute(stmt)
            total += len(payload)
        await session.commit()
    return total


def _chunked(rows: list[UniverseRow], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Tier 1 reference universe (P1.7).")
    parser.add_argument("--kr-only", action="store_true", help="Skip US (S&P 500) seed")
    parser.add_argument("--us-only", action="store_true", help="Skip KR (dartlab listing) seed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.kr_only and args.us_only:
        parser.error("--kr-only and --us-only are mutually exclusive")
    include_kr = not args.us_only
    include_us = not args.kr_only

    summary = asyncio.run(seed_universe(include_kr=include_kr, include_us=include_us))
    logger.info("seed_universe summary: %s", summary)
    print(f"seed_universe: {summary}")


if __name__ == "__main__":
    main()
