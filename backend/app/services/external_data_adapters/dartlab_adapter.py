"""Dartlab adapter — KR DART primary + US analysis() boost layer.

Direct calls to dartlab Python library (Apache 2.0). MCP `_executeTool` is
bypassed entirely — 0.9.26 has broken tool dispatchers (companyFinancials,
companyRatios, searchCompany, ...). Re-instantiates Company per call
(HF disk cache makes warm calls ~0.45s); only normalized output is held by
ResultCache. The 1.5GB Company object never sits in our cache (spec §2 #13).

US is a boost layer here, not primary. `Company('TSLA').rawFinance` raises
AttributeError, and `companyAnalysis` cold load is ~21s. SEC EDGAR is the
US primary (sec_edgar_adapter.py, spec §3 routing).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.external_data_adapters.base import (
    ExternalAdapter,
    FinancialSeries,
    IdentityFacts,
    IndustryGraph,
    SectorInfo,
)
from app.services.external_data_adapters.cache import ResultCache

logger = logging.getLogger(__name__)


class DartlabAdapter(ExternalAdapter):
    """KR DART primary, US boost layer. Emits only standard schema types."""

    def __init__(self, cache: ResultCache | None = None) -> None:
        self._cache = cache or ResultCache()

    async def fetch_identity(self, ticker: str) -> IdentityFacts:
        return await self._cache.get_or_fetch(
            (ticker, "identity"), lambda: self._fetch_identity(ticker)
        )

    async def _fetch_identity(self, ticker: str) -> IdentityFacts:
        c = await asyncio.to_thread(_load_company, ticker)
        market = c.market
        return IdentityFacts(
            ticker=c.stockCode,
            name=c.corpName,
            market=market,
            currency=c.currency,
            fiscal_year_end=getattr(c, "fiscalYearEnd", None),
            corp_code=getattr(c, "corpCode", None) if market == "KR" else None,
            cik=getattr(c, "cik", None) if market == "US" else None,
            fetched_at=datetime.now(timezone.utc),
            source="dartlab",
        )

    async def fetch_financial_series(self, ticker: str) -> FinancialSeries:
        return await self._cache.get_or_fetch(
            (ticker, "financials"), lambda: self._fetch_financials(ticker)
        )

    async def _fetch_financials(self, ticker: str) -> FinancialSeries:
        c = await asyncio.to_thread(_load_company, ticker)
        if c.market == "KR":
            rows = await asyncio.to_thread(_kr_rows_from_company, c)
        else:
            rows = await asyncio.to_thread(_us_rows_from_company, c)
        return FinancialSeries(
            ticker=c.stockCode,
            period_type="annual",
            rows=rows,
            source="dartlab",
            fetched_at=datetime.now(timezone.utc),
        )

    async def fetch_sector(self, ticker: str) -> SectorInfo | None:
        c = await asyncio.to_thread(_load_company, ticker)
        if c.market != "KR":
            return None  # US sector → sec_edgar_adapter (spec §6)
        si = c.sector
        if si is None:
            return None
        return SectorInfo(
            sector=str(si.sector),
            industry_group=_safe_industry_group(si),
            confidence=float(getattr(si, "confidence", 0.0)),
            source="dartlab",
        )

    async def fetch_industry_graph(self, industry_id: str) -> IndustryGraph:
        graph = await asyncio.to_thread(_load_industry, industry_id)
        if not isinstance(graph, dict):
            graph = {}
        return IndustryGraph(
            industry_id=industry_id,
            nodes=graph.get("nodes", []),
            edges=graph.get("edges", []),
            source="dartlab",
        )


def _load_company(ticker: str) -> Any:
    """Sync dartlab Company instantiation (~0.45s warm after HF disk cache).

    Raises ValueError on miss; propagated to caller (silent fallback X).
    Imports at call time so module import doesn't pull dartlab eagerly.
    """
    import dartlab
    return dartlab.Company(ticker)


def _load_industry(industry_id: str) -> Any:
    import dartlab
    return dartlab.industry(industry_id)


def _safe_industry_group(si: Any) -> str | None:
    raw = getattr(si, "industryGroup", None)
    if raw is None:
        return None
    s = str(raw)
    return s if s and s != "None" else None


def _kr_rows_from_company(c: Any) -> list[dict]:
    """polars rawFinance → year-grouped row-count summary.

    Phase A delivers schema only. Accurate IS/BS/CF roll-up (revenue,
    op income, net income aggregation) is deferred to Phase B, when the
    existing `data_layer._fetch_fundamentals` is wired up for A/B
    comparison and we can validate against known-good outputs.
    """
    df = getattr(c, "rawFinance", None)
    if df is None:
        return []
    try:
        records = df.to_dicts()
    except Exception:  # noqa: BLE001 — defensive against non-polars-shaped input
        return []
    return _records_to_year_rows(records)


def _us_rows_from_company(c: Any) -> list[dict]:
    """US `c.rawFinance` raises AttributeError; fall back to `analysis('수익성')`.

    Boost layer only — SEC EDGAR adapter is the US truth source.
    """
    try:
        margin = c.analysis("수익성")
    except Exception as e:  # noqa: BLE001 — US analysis can fail or be slow
        logger.warning("dartlab US analysis failed for %s: %s", c.stockCode, e)
        return []
    if not isinstance(margin, dict):
        return []
    trend = margin.get("marginTrend", {})
    history = trend.get("history", []) if isinstance(trend, dict) else []
    if not isinstance(history, list):
        return []
    return [
        {
            "period": h.get("period"),
            "revenue": h.get("revenue"),
            "operating_income": h.get("operatingIncome"),
            "operating_margin": h.get("operatingMargin"),
            "net_income": h.get("netIncome"),
        }
        for h in history
        if isinstance(h, dict)
    ]


def _records_to_year_rows(records: list[dict]) -> list[dict]:
    by_year: dict[str, int] = {}
    for r in records:
        y = r.get("bsns_year")
        if isinstance(y, str) and y:
            by_year[y] = by_year.get(y, 0) + 1
    return sorted(
        ({"period": y, "row_count": cnt} for y, cnt in by_year.items()),
        key=lambda x: x["period"],
    )
