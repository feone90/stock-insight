"""Ontology relation extraction (P1.6).

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §4, §6

v0 ships:
  - `universe_wide_sector_match` — Tier 1+2 양방향 peer cross-match
  - `scan_pending_candidates(stock_id)` — Tier 3→1/2 promote hook (P1.7 trigger)
"""

from app.services.ontology.sector_match import universe_wide_sector_match
from app.services.ontology.upsert import (
    bulk_upsert_relations,
    scan_pending_candidates,
)

__all__ = [
    "bulk_upsert_relations",
    "scan_pending_candidates",
    "universe_wide_sector_match",
]
