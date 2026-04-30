"""Universe-wide bidirectional sector match (P1.6 v0).

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6.1
Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6.1

P1.5 `onto_hook.enrich_stock_after_register` only emits a single direction
edge (newly-registered → existing peer). v0 fixes both:
  - bidirectional rows (a→b and b→a)
  - applied across the entire Tier 1+2 universe in one nightly pass

Per-sector cap (`SECTOR_PAIR_CAP`) bounds explosion. KSIC is more fragmented
than GICS 11 so top sectors (소프트웨어, 특수목적 기계, 전자부품 ...) carry 100+
members; without cap a single sector emits C(189,2)×2 = ~35K rows. Cap 30 →
worst-case sector emits ~870 rows; total network sits in the ~30-60K range.

Cap ordering: market_cap DESC (NULLS LAST), then ticker ASC. Phase A leaves
market_cap=None for all KR rows so the tiebreaker (ticker ASC) is the
de-facto Phase A ordering — deterministic and stable across re-runs.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Stock
from app.services.ontology.upsert import bulk_upsert_relations

logger = logging.getLogger(__name__)

SECTOR_PAIR_CAP = 30
_TIER_USER_TOUCHED = 2
_PEER_SOURCE = "sector_match"
_PEER_RELATION = "peer"
_DEFAULT_STRENGTH = 0.5
_DEFAULT_CONFIDENCE = 0.4  # objective sector match — strong signal but not certainty


async def universe_wide_sector_match(
    *, session: AsyncSession | None = None
) -> dict:
    """Re-run the universe-wide sector cross-match.

    Idempotent — ON CONFLICT DO UPDATE in `bulk_upsert_relations` smooths
    re-runs (strength averaged, confidence MAX, refreshed_at bumped).
    Pass `session` to reuse caller transaction (test fixtures).
    """
    if session is not None:
        return await _run(session)
    async with async_session() as own:
        summary = await _run(own)
        await own.commit()
        return summary


async def _run(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Stock).where(
            Stock.tier <= _TIER_USER_TOUCHED,
            Stock.is_delisted.is_(False),
        )
    )
    stocks = result.scalars().all()

    by_sector: dict[str, list[Stock]] = defaultdict(list)
    for s in stocks:
        if not s.sector or s.sector == "Unknown":
            continue
        by_sector[s.sector].append(s)

    rows: list[dict] = []
    capped_sectors = 0
    for sector, members in by_sector.items():
        if len(members) < 2:
            continue
        ranked = sorted(
            members,
            key=lambda s: (
                s.market_cap is None,  # NULLS LAST
                -(float(s.market_cap) if s.market_cap is not None else 0.0),
                s.ticker,
            ),
        )
        if len(ranked) > SECTOR_PAIR_CAP:
            ranked = ranked[:SECTOR_PAIR_CAP]
            capped_sectors += 1

        for a, b in combinations(ranked, 2):
            rows.append(_make_peer_row(a, b))
            rows.append(_make_peer_row(b, a))

    upserted = await bulk_upsert_relations(rows, session=session)
    summary = {
        "stocks_in_universe": len(stocks),
        "sectors": len(by_sector),
        "sectors_capped": capped_sectors,
        "pair_rows": len(rows),
        "upserted": upserted,
    }
    logger.info("universe_wide_sector_match: %s", summary)
    return summary


def _make_peer_row(a: Stock, b: Stock) -> dict:
    return {
        "from_stock_id": a.id,
        "to_target": b.ticker,
        "to_kind": "stock",
        "relation_type": _PEER_RELATION,
        "strength": _DEFAULT_STRENGTH,
        "source": _PEER_SOURCE,
        "signal_direction": "positive",
        "confidence": _DEFAULT_CONFIDENCE,
    }
