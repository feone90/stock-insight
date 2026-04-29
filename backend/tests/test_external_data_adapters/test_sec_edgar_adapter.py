"""SecEdgarAdapter — spec §6 7 unit cases (httpx MockTransport)."""
import json

import httpx
import pytest

from app.services.external_data_adapters.cache import ResultCache
from app.services.external_data_adapters.sec_edgar_adapter import (
    SecEdgarAdapter,
    _normalize_xbrl_to_rows,
    _parse_ticker_payload,
)


@pytest.fixture(autouse=True)
def _set_ua(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "test-agent test@example.com")


def _ticker_payload() -> dict:
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
    }


def _aapl_facts_payload() -> dict:
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"fy": 2022, "fp": "FY", "val": 394328000000},
                            {"fy": 2023, "fp": "FY", "val": 383285000000},
                            {"fy": 2024, "fp": "FY", "val": 391035000000},
                            {"fy": 2024, "fp": "Q3", "val": 100000000000},  # ignored
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "val": 96995000000},
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "val": 364980000000},
                        ]
                    }
                },
            }
        },
    }


def _aapl_submissions_payload() -> dict:
    return {
        "cik": "320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "fiscalYearEnd": "0928",
        "sic": "3571",
        "sicDescription": "Electronic Computers",
    }


def _make_handler(routes: dict[str, httpx.Response]):
    """Match by URL substring (first hit wins)."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for needle, resp in routes.items():
            if needle in url:
                return resp
        return httpx.Response(404, json={"error": "no route"})
    return handler


def _client_with(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(_make_handler(routes)),
        headers={"User-Agent": "test-agent test@example.com"},
    )


@pytest.mark.asyncio
async def test_fetch_financial_series_ok_response_extracts_fy_rows():
    routes = {
        "company_tickers.json": httpx.Response(200, json=_ticker_payload()),
        "companyfacts/CIK0000320193": httpx.Response(200, json=_aapl_facts_payload()),
    }
    adapter = SecEdgarAdapter(cache=ResultCache(), client=_client_with(routes))
    series = await adapter.fetch_financial_series("AAPL")
    assert series.source == "sec_edgar"
    assert series.ticker == "AAPL"
    periods = [r["period"] for r in series.rows]
    assert periods == ["2022", "2023", "2024"]  # quarterly entry filtered out
    fy24 = next(r for r in series.rows if r["period"] == "2024")
    assert fy24["revenue"] == 391035000000
    assert fy24["net_income"] == 96995000000
    assert fy24["assets"] == 364980000000


@pytest.mark.asyncio
async def test_fetch_financial_series_empty_xbrl_units_returns_empty_rows():
    empty_facts = {"cik": 320193, "facts": {"us-gaap": {}}}
    routes = {
        "company_tickers.json": httpx.Response(200, json=_ticker_payload()),
        "companyfacts/CIK0000320193": httpx.Response(200, json=empty_facts),
    }
    adapter = SecEdgarAdapter(cache=ResultCache(), client=_client_with(routes))
    series = await adapter.fetch_financial_series("AAPL")
    assert series.rows == []  # silent quality 저하 방지: empty rows + warning log


@pytest.mark.asyncio
async def test_503_retried_then_raises_on_exhaustion():
    routes = {
        "company_tickers.json": httpx.Response(200, json=_ticker_payload()),
        "companyfacts/CIK0000320193": httpx.Response(503),
    }
    adapter = SecEdgarAdapter(cache=ResultCache(), client=_client_with(routes))
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.fetch_financial_series("AAPL")


@pytest.mark.asyncio
async def test_429_backoff_then_success_on_retry():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=_ticker_payload())
        if "companyfacts/CIK0000320193" in url:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(429)
            return httpx.Response(200, json=_aapl_facts_payload())
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SecEdgarAdapter(cache=ResultCache(), client=client)
    series = await adapter.fetch_financial_series("AAPL")
    assert series.source == "sec_edgar"
    assert call_count["n"] == 2  # initial 429 + retry succeed


@pytest.mark.asyncio
async def test_unknown_ticker_raises_value_error():
    routes = {
        "company_tickers.json": httpx.Response(200, json=_ticker_payload()),
    }
    adapter = SecEdgarAdapter(cache=ResultCache(), client=_client_with(routes))
    with pytest.raises(ValueError, match="no CIK"):
        await adapter.fetch_financial_series("NOPE")


@pytest.mark.asyncio
async def test_sic_hit_returns_high_confidence_sector():
    routes = {
        "company_tickers.json": httpx.Response(200, json=_ticker_payload()),
        "submissions/CIK0000320193": httpx.Response(200, json=_aapl_submissions_payload()),
    }
    adapter = SecEdgarAdapter(cache=ResultCache(), client=_client_with(routes))
    sector = await adapter.fetch_sector("AAPL")
    assert sector.sector == "Information Technology"
    assert sector.industry_group == "Technology Hardware & Equipment"
    assert sector.confidence == 0.7  # SIC_MAPPING_HIT_CONFIDENCE
    assert sector.source == "sec_edgar_sic"


@pytest.mark.asyncio
async def test_sic_miss_returns_unknown_with_low_confidence():
    unmapped = dict(_aapl_submissions_payload())
    unmapped["sic"] = "9999"  # not in our static map
    routes = {
        "company_tickers.json": httpx.Response(200, json=_ticker_payload()),
        "submissions/CIK0000320193": httpx.Response(200, json=unmapped),
    }
    adapter = SecEdgarAdapter(cache=ResultCache(), client=_client_with(routes))
    sector = await adapter.fetch_sector("AAPL")
    assert sector.sector == "Unknown"
    assert sector.industry_group is None
    assert sector.confidence == 0.3  # SIC_MAPPING_MISS_CONFIDENCE


# ---------------------------------------------------------------------------
# Pure helpers (covered alongside; trivial)
# ---------------------------------------------------------------------------


def test_parse_ticker_payload_filters_invalid_entries():
    raw = {
        "0": {"cik_str": 1, "ticker": "A"},
        "1": {"cik_str": "not-int", "ticker": "B"},  # rejected
        "2": "not-dict",  # rejected
    }
    assert _parse_ticker_payload(raw) == {"A": "1"}


def test_normalize_xbrl_handles_non_dict_input():
    assert _normalize_xbrl_to_rows(None) == []
    assert _normalize_xbrl_to_rows({}) == []
    assert _normalize_xbrl_to_rows({"facts": "wrong"}) == []
