"""Ontology relation extraction (P1.6).

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §4, §6

v0 (sector_match) — 머지됨.
v1 (LLM RAG common): schemas / prompts / extractor / validator — 본 chunk.
v1 DART adapter / v2 SEC adapter는 별도 chunk.
"""

from app.services.ontology.correlation import (
    compute_pairwise_correlation,
    verify_inverse_signals,
)
from app.services.ontology.extract_news import (
    extract_news_relations_for_ticker,
    extract_news_relations_for_universe,
)
from app.services.ontology.extract_10k_risk import (
    extract_10k_risk,
    extract_10k_risk_for_universe,
)
from app.services.ontology.extract_dart_contract import (
    extract_dart_contracts,
    extract_dart_contracts_for_universe,
)
from app.services.ontology.extract_sec import (
    extract_sec_contracts,
    extract_sec_contracts_for_universe,
)
from app.services.ontology.regulatory_coshock import extract_regulatory_coshock
from app.services.ontology.extractor import extract_relations
from app.services.ontology.schemas import (
    ExtractedRelation,
    ExtractionBatch,
    RelationType,
    SignalDirection,
)
from app.services.ontology.sector_match import universe_wide_sector_match
from app.services.ontology.upsert import (
    bulk_upsert_relations,
    scan_pending_candidates,
)
from app.services.ontology.validator import validate_and_route

__all__ = [
    "ExtractedRelation",
    "ExtractionBatch",
    "RelationType",
    "SignalDirection",
    "bulk_upsert_relations",
    "compute_pairwise_correlation",
    "extract_10k_risk",
    "extract_10k_risk_for_universe",
    "extract_dart_contracts",
    "extract_dart_contracts_for_universe",
    "extract_regulatory_coshock",
    "extract_news_relations_for_ticker",
    "extract_news_relations_for_universe",
    "extract_relations",
    "extract_sec_contracts",
    "extract_sec_contracts_for_universe",
    "scan_pending_candidates",
    "universe_wide_sector_match",
    "validate_and_route",
    "verify_inverse_signals",
]
