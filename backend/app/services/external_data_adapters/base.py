"""Standard schema + ABC for external data adapters.

All adapters (DartlabAdapter, SecEdgarAdapter) emit only these schema types;
their internal vendor representations (dartlab Company / SEC XBRL) are never
exposed to the rest of the app. v2 card layer reads only these models.
"""
from __future__ import annotations

from abc import ABC
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Market = Literal["KR", "US"]
PeriodType = Literal["annual", "quarterly", "ttm"]


class IdentityFacts(BaseModel):
    """종목 메타 — 카드 헤더에 박히는 정보."""

    ticker: str
    name: str
    market: Market
    currency: str
    fiscal_year_end: str | None = None
    cik: str | None = None
    corp_code: str | None = None
    fetched_at: datetime
    source: str


class SectorInfo(BaseModel):
    """sector 분류. dartlab SectorInfo / SEC SIC + GICS 매핑 통합 표면."""

    sector: str
    industry_group: str | None = None
    confidence: float = Field(ge=0, le=1)
    source: Literal["dartlab", "sec_edgar_sic", "static_mapping"]


class FinancialSeries(BaseModel):
    """5y+ 재무 시계열. KR rawFinance / US XBRL company facts 정규화."""

    ticker: str
    period_type: PeriodType
    rows: list[dict]
    source: str
    fetched_at: datetime


class FundamentalsSnapshot(BaseModel):
    """단일 시점 재무 비율. data_layer._fetch_fundamentals 대체 후보 (Phase B)."""

    per: float | None = None
    pbr: float | None = None
    market_cap: float | None = None
    dividend_yield: float | None = None
    per_5y_z: float | None = None
    period_label: str
    source: str


class IndustryGraph(BaseModel):
    """KR dartlab.industry() 산업지도 raw → onto 후보 source."""

    industry_id: str
    nodes: list[dict]
    edges: list[dict]
    source: Literal["dartlab"]


class ExternalAdapter(ABC):
    """Marker base. Concrete adapters expose `fetch_*` methods relevant to their
    market — `DartlabAdapter` adds `fetch_industry_graph` (KR-only),
    `SecEdgarAdapter` adds `fetch_fiscal_year_end` (US-only). The router in
    `__init__.py:get_adapter_for(ticker)` returns the correct concrete type."""
