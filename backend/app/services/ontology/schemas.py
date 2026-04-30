"""Pydantic schemas for LLM-extracted relations.

Source-agnostic — same shape used for DART, SEC 8-K, news, web extraction.
LLM returns a JSON array of `ExtractedRelation`; the extractor wraps it in
`ExtractionBatch` for retry/validation control.

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6
Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RelationType = Literal[
    "peer",
    "supply_upstream",
    "supply_downstream",
    "group",
    "theme",
    "macro",
    "competitor",
    "contract_supplier",
    "contract_customer",
    "complementary",
    "regulatory_link",
]
SignalDirection = Literal["positive", "negative", "inverse"]


class ExtractedRelation(BaseModel):
    """One LLM-extracted edge between two stocks.

    Tickers are validated up-front (non-empty, normalized to uppercase for
    US, kept as-is for KR 6-digit). Universe matching happens in `validator`.
    """

    model_config = ConfigDict(extra="ignore")  # tolerate LLM key drift

    from_ticker: str
    to_ticker: str
    relation_type: RelationType
    signal_direction: SignalDirection = "positive"
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    valid_from: date | None = None
    valid_until: date | None = None
    rationale: str | None = None
    extra_metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata")

    @field_validator("from_ticker", "to_ticker", mode="before")
    @classmethod
    def _normalize_ticker(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("ticker must be a string")
        v = v.strip()
        if not v:
            raise ValueError("ticker must be non-empty")
        # KR 6-digit numeric — keep as-is. US/anything else — uppercase.
        return v if v.isdigit() else v.upper()


class ExtractionBatch(BaseModel):
    """Wrapper so the LLM can return either a bare array or `{"relations": [...]}`."""

    relations: list[ExtractedRelation] = Field(default_factory=list)
