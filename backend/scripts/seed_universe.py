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

from app.services.universe import (
    UniverseRow,
    fetch_kr_universe,
    fetch_us_universe,
)
from app.services.universe.upsert import bulk_upsert_tier1, dedupe_by_ticker

logger = logging.getLogger(__name__)


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

    deduped = dedupe_by_ticker(rows)
    upserted = await bulk_upsert_tier1(deduped)
    return {"fetched": len(rows), "deduped": len(deduped), "upserted": upserted}


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
