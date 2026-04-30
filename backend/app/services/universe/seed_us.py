"""US Reference Universe seed via Wikipedia S&P 500 list.

Plan: docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md §7
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §3.1

S&P 500 membership is the seed source — wikipedia maintains a clean
HTML table at /wiki/List_of_S%26P_500_companies with GICS sector and
sub-industry columns. CIK column lets P1.6 SEC EDGAR cross-match without
an extra `fetch_identity` round trip. market_cap is not in the table;
backfill comes later (Phase A.5 or P1.6 LLM RAG).
"""
from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup, Tag

from app.services.universe.types import UniverseRow

logger = logging.getLogger(__name__)

US_SP500_SOURCE = "sp500_index"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_USER_AGENT = "StockInsight/0.1 (yohan1422@gmail.com)"
_FETCH_TIMEOUT = 30.0


async def fetch_us_universe() -> list[UniverseRow]:
    """Fetch S&P 500 list from wikipedia.

    Returns [] on fetch / parse failure (caller decides whether to abort or
    proceed KR-only). Logs at WARNING so failures show up in scheduler logs.
    """
    try:
        html = await _fetch_html(SP500_URL)
    except Exception as e:  # noqa: BLE001 — network/timeout/etc
        logger.warning("Wikipedia S&P 500 fetch failed: %s", e)
        return []

    rows = _parse_sp500_table(html)
    logger.info("US universe: %d S&P 500 rows parsed", len(rows))
    return rows


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
        timeout=_FETCH_TIMEOUT,
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


def _parse_sp500_table(html: str) -> list[UniverseRow]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "constituents"})
    if not isinstance(table, Tag):
        logger.warning("S&P 500 wikipedia: table#constituents not found")
        return []

    tbody = table.find("tbody")
    if not isinstance(tbody, Tag):
        return []

    rows: list[UniverseRow] = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        normalized = _normalize_sp500_row(cells)
        if normalized is not None:
            rows.append(normalized)
    return rows


def _normalize_sp500_row(cells: list[Tag]) -> UniverseRow | None:
    if len(cells) < 4:
        return None
    ticker = cells[0].get_text(strip=True)
    name = cells[1].get_text(strip=True)
    sector = cells[2].get_text(strip=True)
    sub_industry = cells[3].get_text(strip=True)
    if not ticker or not name or not sector:
        return None
    return UniverseRow(
        ticker=ticker,
        name=name,
        market="US",
        sector=sector,
        industry_group=sub_industry or None,
        listing_date=None,
        universe_source=US_SP500_SOURCE,
    )
