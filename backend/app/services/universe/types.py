"""Shared types for universe seed modules."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UniverseRow:
    """One row of Tier 1 reference universe candidate.

    Phase A populates from objective sources (KRX listing / S&P 500 wikipedia).
    market_cap / avg_volume_30d are None unless source provides them; later
    phases backfill via per-ticker fetch.
    """

    ticker: str
    name: str
    market: str  # "KOSPI" / "KOSDAQ" / "US"
    sector: str  # KSIC for KR, GICS sector for US
    industry_group: str | None
    listing_date: str | None  # ISO date string when known
    universe_source: str  # e.g. "kospi_listing", "kosdaq_listing", "sp500_index"
