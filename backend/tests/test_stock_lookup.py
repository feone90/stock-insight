from types import SimpleNamespace

import pytest

from app.collectors import stock_lookup


def test_lookup_yfinance_search_finds_us_company_name(monkeypatch):
    class FakeSearch:
        def __init__(self, query, max_results):
            assert query == "Bloom Energy"
            assert max_results == 10
            self.quotes = [
                {
                    "quoteType": "EQUITY",
                    "symbol": "BE",
                    "exchange": "NYQ",
                    "longname": "Bloom Energy Corporation",
                    "sector": "Industrials",
                },
                {
                    "quoteType": "EQUITY",
                    "symbol": "BE.MX",
                    "exchange": "MEX",
                    "longname": "Bloom Energy Corporation",
                },
                {
                    "quoteType": "ETF",
                    "symbol": "BETH",
                    "exchange": "NMS",
                    "longname": "Not an equity",
                },
            ]

    monkeypatch.setitem(
        __import__("sys").modules,
        "yfinance",
        SimpleNamespace(Search=FakeSearch),
    )

    results = stock_lookup._lookup_yfinance_search("Bloom Energy")

    assert results == [
        {
            "ticker": "BE",
            "name": "Bloom Energy Corporation",
            "market": "NYSE",
            "sector": "Industrials",
            "current_price": 0,
        }
    ]


@pytest.mark.asyncio
async def test_search_external_includes_yfinance_company_search(monkeypatch):
    monkeypatch.setattr(stock_lookup, "_lookup_fdr", lambda query: [])
    monkeypatch.setattr(stock_lookup, "_lookup_yfinance", lambda query: [])
    monkeypatch.setattr(
        stock_lookup,
        "_lookup_yfinance_search",
        lambda query: [{
            "ticker": "BE",
            "name": "Bloom Energy Corporation",
            "market": "NYSE",
            "sector": "Industrials",
            "current_price": 0,
        }],
    )

    results = await stock_lookup.search_external("Bloom Energy")

    assert [item["ticker"] for item in results] == ["BE"]
