"""KR Reference Universe seed via `dartlab.listing(market='KR')`.

Plan: docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md §6
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §3.1

Phase A — pulls all KRX-listed companies (KOSPI + KOSDAQ, ~2,556 rows),
drops KONEX (코넥스, ~110 microcap names). market_cap is unavailable from
the listing endpoint so each row carries `None`; Phase A.5 backfills via
per-ticker fetch. Sector quota intentionally not applied here (no rank
metric in source data); see sector_quota.py for the future hookup.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.universe.types import UniverseRow

logger = logging.getLogger(__name__)

KR_KOSPI_SOURCE = "kospi_listing"
KR_KOSDAQ_SOURCE = "kosdaq_listing"

_MARKET_SEGMENT_MAP = {
    "유가": "KOSPI",
    "코스닥": "KOSDAQ",
}
_SOURCE_BY_MARKET = {
    "KOSPI": KR_KOSPI_SOURCE,
    "KOSDAQ": KR_KOSDAQ_SOURCE,
}


async def fetch_kr_universe() -> list[UniverseRow]:
    """Fetch and normalize KR Tier 1 universe.

    Returns empty list (with warning) on dartlab failure — caller decides
    whether to abort the seed run or continue with US-only.
    """
    try:
        records = await asyncio.to_thread(_fetch_listing_records)
    except Exception as e:  # noqa: BLE001 — dartlab can raise anything
        logger.warning("dartlab.listing(market='KR') failed: %s", e)
        return []

    rows: list[UniverseRow] = []
    for rec in records:
        normalized = _normalize_kr_row(rec)
        if normalized is not None:
            rows.append(normalized)
    logger.info("KR universe: %d candidates from %d listing records", len(rows), len(records))
    return rows


def _fetch_listing_records() -> list[dict[str, Any]]:
    """Sync dartlab call — wrapped by `asyncio.to_thread` in fetch_kr_universe."""
    import dartlab

    df = dartlab.listing(market="KR")
    return df.to_dicts()


def _normalize_kr_row(rec: dict[str, Any]) -> UniverseRow | None:
    """Map dartlab listing schema → UniverseRow. Returns None for KONEX/invalid."""
    segment = rec.get("시장구분")
    market = _MARKET_SEGMENT_MAP.get(segment) if isinstance(segment, str) else None
    if market is None:
        return None  # KONEX (코넥스) and unknown segments are dropped

    ticker = rec.get("종목코드")
    name = rec.get("회사명")
    if not isinstance(ticker, str) or not ticker:
        return None
    if not isinstance(name, str) or not name:
        return None

    sector = rec.get("업종")
    if not isinstance(sector, str) or not sector:
        sector = "Unknown"

    products = rec.get("주요제품")
    industry_group = products if isinstance(products, str) and products else None

    listing_date = rec.get("상장일")
    listing_date_str = listing_date if isinstance(listing_date, str) and listing_date else None

    return UniverseRow(
        ticker=ticker,
        name=name,
        market=market,
        sector=sector,
        industry_group=industry_group,
        listing_date=listing_date_str,
        universe_source=_SOURCE_BY_MARKET[market],
    )
