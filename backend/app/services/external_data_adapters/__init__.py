"""External data adapters — KR DART (dartlab) + US SEC EDGAR.

P1.5 milestone. See docs/superpowers/specs/2026-04-29-external-data-adapters.md.

Public API: `get_adapter_for(ticker)` — routes a raw ticker to its primary
adapter (KR → DartlabAdapter, US → SecEdgarAdapter). Adapters share a single
process-wide `ResultCache` keyed by `(ticker, method)`.
"""
from app.services.external_data_adapters.base import (
    ExternalAdapter,
    FinancialSeries,
    FundamentalsSnapshot,
    IdentityFacts,
    IndustryGraph,
    SectorInfo,
)
from app.services.external_data_adapters.cache import ResultCache
from app.services.external_data_adapters.dartlab_adapter import DartlabAdapter
from app.services.external_data_adapters.sec_edgar_adapter import SecEdgarAdapter
from app.services.external_data_adapters.ticker import normalize_ticker

# Process-wide cache; keyed on `(ticker, method)` so adapters don't collide.
_shared_cache = ResultCache()
_dartlab_singleton: DartlabAdapter | None = None
_sec_edgar_singleton: SecEdgarAdapter | None = None


def get_adapter_for(ticker: str) -> ExternalAdapter:
    """Route a raw ticker to its primary adapter.

    KR (6-digit) → DartlabAdapter
    US (alpha)   → SecEdgarAdapter   (dartlab is boost-only here, called by
                                       data_layer when it wants `analysis()`)
    """
    _, market = normalize_ticker(ticker)
    if market == "KR":
        return _get_dartlab()
    return _get_sec_edgar()


def _get_dartlab() -> DartlabAdapter:
    global _dartlab_singleton
    if _dartlab_singleton is None:
        _dartlab_singleton = DartlabAdapter(cache=_shared_cache)
    return _dartlab_singleton


def _get_sec_edgar() -> SecEdgarAdapter:
    global _sec_edgar_singleton
    if _sec_edgar_singleton is None:
        _sec_edgar_singleton = SecEdgarAdapter(cache=_shared_cache)
    return _sec_edgar_singleton


__all__ = [
    "DartlabAdapter",
    "ExternalAdapter",
    "FinancialSeries",
    "FundamentalsSnapshot",
    "IdentityFacts",
    "IndustryGraph",
    "ResultCache",
    "SecEdgarAdapter",
    "SectorInfo",
    "get_adapter_for",
    "normalize_ticker",
]
