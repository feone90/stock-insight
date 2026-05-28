from types import SimpleNamespace

import pytest

from app.collectors import stock_lookup
from app.models import Stock


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


def test_lookup_yfinance_skips_bare_numeric_kr_artifacts(monkeypatch):
    seen: list[str] = []

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol
            seen.append(symbol)

        @property
        def info(self):
            if self.symbol == "010620.KS":
                return {
                    "symbol": "010620.KS",
                    "shortName": "010620.KQ,0P0000AV7F,338404",
                    "exchange": "KSC",
                }
            if self.symbol == "010620.KQ":
                return {
                    "symbol": "010620.KQ",
                    "shortName": "HD현대미포",
                    "exchange": "KSC",
                    "currentPrice": 97000,
                }
            return {}

    monkeypatch.setitem(
        __import__("sys").modules,
        "yfinance",
        SimpleNamespace(Ticker=FakeTicker),
    )

    results = stock_lookup._lookup_yfinance("010620")

    assert seen == ["010620.KS", "010620.KQ"]
    assert results == [{
        "ticker": "010620",
        "name": "HD현대미포",
        "market": "KRX",
        "sector": "",
        "current_price": 97000,
    }]


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


@pytest.mark.asyncio
async def test_register_stock_prefers_fdr_for_kr_ticker(monkeypatch, db):
    monkeypatch.setattr(
        stock_lookup,
        "_lookup_fdr",
        lambda query: [{
            "ticker": query,
            "name": "HD현대미포",
            "market": "KOSPI",
            "sector": "운송장비",
            "current_price": 97000,
        }],
    )

    def fail_yfinance(query):
        raise AssertionError("Korean 6-digit registration should try FDR first")

    monkeypatch.setattr(stock_lookup, "_lookup_yfinance", fail_yfinance)

    stock = await stock_lookup.register_stock(db, "999888")

    assert stock is not None
    assert stock.ticker == "999888"
    assert stock.name == "HD현대미포"
    assert stock.market == "KOSPI"


@pytest.mark.asyncio
async def test_repair_stock_metadata_replaces_malformed_kr_name(monkeypatch, db):
    stock = Stock(
        ticker="999889",
        name="999889.KQ,0P0000AV7F,338404",
        market="KRX",
        sector="",
        current_price=1,
    )
    db.add(stock)
    await db.flush()

    monkeypatch.setattr(
        stock_lookup,
        "_lookup_fdr",
        lambda query: [{
            "ticker": query,
            "name": "정상종목명",
            "market": "KOSPI",
            "sector": "산업재",
            "current_price": 12345,
        }],
    )

    repaired = await stock_lookup.repair_stock_metadata_if_needed(db, stock)

    assert repaired.name == "정상종목명"
    assert repaired.market == "KOSPI"
    assert repaired.sector == "산업재"
    assert repaired.current_price == 12345
