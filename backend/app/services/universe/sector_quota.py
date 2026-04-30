"""GICS / KSIC sector quota algorithm.

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §3.1
Plan: docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md §6.3

Phase A doesn't apply this — KR seed takes all KOSPI+KOSDAQ from
dartlab.listing() (no market_cap to rank by). The function is wired up
here so Phase A.5 (market_cap backfill) and Phase B (nightly refresh)
can use it without restructuring callers.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from app.services.universe.types import UniverseRow

RankKey = Callable[[UniverseRow], float | None]


def apply_sector_quota(
    candidates: list[UniverseRow],
    pool: list[UniverseRow],
    min_per_sector: int,
    rank_key: RankKey | None = None,
) -> list[UniverseRow]:
    """Top up under-represented sectors from `pool`.

    For each sector with fewer than `min_per_sector` rows in `candidates`,
    pull the missing count from `pool` (rows not already in candidates),
    ranked by `rank_key` descending — None ranks last, ties broken by ticker.

    `rank_key=None` keeps pool input order (Phase A — no metric to rank by).
    """
    if min_per_sector <= 0:
        return list(candidates)

    by_sector_count: dict[str, int] = defaultdict(int)
    candidate_tickers: set[str] = set()
    for row in candidates:
        by_sector_count[row.sector] += 1
        candidate_tickers.add(row.ticker)

    pool_by_sector: dict[str, list[UniverseRow]] = defaultdict(list)
    for row in pool:
        if row.ticker in candidate_tickers:
            continue
        pool_by_sector[row.sector].append(row)

    additions: list[UniverseRow] = []
    for sector, sector_pool in pool_by_sector.items():
        deficit = min_per_sector - by_sector_count.get(sector, 0)
        if deficit <= 0:
            continue
        if rank_key is not None:
            sector_pool = sorted(
                sector_pool,
                key=lambda r: (
                    rank_key(r) is None,
                    -(rank_key(r) or 0.0),
                    r.ticker,
                ),
            )
        additions.extend(sector_pool[:deficit])

    return list(candidates) + additions
