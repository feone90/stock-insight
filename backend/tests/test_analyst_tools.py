"""Unit tests for analyst tools. DB tools use the test DB fixture; LLM/web tools
are mocked in their own tests later.

The tools call `async_session()` internally — that opens a new connection that
doesn't see SAVEPOINT-isolated test writes. We monkey-patch `async_session` per
test (autouse fixture) so tools share the test's session.
"""
from contextlib import asynccontextmanager
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import PriceHistory, Stock
from app.models.relation import StockRelation
from app.services.analyst.tools import (
    get_indicators,
    get_investor_flow,
    get_relations,
)


@pytest_asyncio.fixture
async def db_for_tools(db, monkeypatch):
    """`db` session + monkeypatch so analyst tools use it for `async_session()`."""

    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("app.services.analyst.tools.async_session", _session)
    return db


@pytest.mark.asyncio
async def test_get_indicators_returns_none_for_missing_stock():
    """No db fixture — runs against the real test DB. NOTREAL doesn't exist there."""
    out = await get_indicators("NOTREAL")
    assert out == {"error": "종목 'NOTREAL'을(를) 찾을 수 없습니다."}


@pytest.mark.asyncio
async def test_get_indicators_returns_indicators_with_enough_data(db_for_tools):
    db = db_for_tools
    # Seed a stock + 60 days of price history
    stock = Stock(ticker="TEST1", name="테스트", market="KRX", sector="기타")
    db.add(stock)
    await db.flush()

    base = date.today() - timedelta(days=80)
    closes_pattern = [100 + i * 0.5 for i in range(70)]
    for i, c in enumerate(closes_pattern):
        db.add(
            PriceHistory(
                stock_id=stock.id,
                date=base + timedelta(days=i),
                open=c - 0.2,
                high=c + 1.0,
                low=c - 1.0,
                close=c,
                volume=1_000_000 + i * 1000,
            )
        )
    await db.commit()

    out = await get_indicators("TEST1")
    assert "rsi_14" in out
    assert out["rsi_14"] is not None
    assert out["ma_stack"] in ("정배열", "역배열", "혼조")
    assert out["citations"][0]["source_type"] == "db"


@pytest.mark.asyncio
async def test_get_relations_empty_when_none_seeded(db_for_tools):
    db = db_for_tools
    stock = Stock(ticker="TEST2", name="테스트2", market="KRX", sector="기타")
    db.add(stock)
    await db.commit()
    out = await get_relations("TEST2", relation_type="peer")
    assert out["relations"] == []


@pytest.mark.asyncio
async def test_get_relations_returns_seeded(db_for_tools):
    db = db_for_tools
    s1 = Stock(ticker="AAA", name="A", market="KRX", sector="X")
    db.add(s1)
    await db.flush()
    db.add(
        StockRelation(
            from_stock_id=s1.id,
            to_target="BBB",
            to_kind="stock",
            relation_type="peer",
            strength=0.8,
        )
    )
    await db.commit()

    out = await get_relations("AAA", relation_type="peer")
    assert len(out["relations"]) == 1
    assert out["relations"][0]["target_ticker"] == "BBB"
    assert out["relations"][0]["strength"] == 0.8


@pytest.mark.asyncio
async def test_get_investor_flow_returns_none_for_us_stock(db_for_tools):
    """US tickers should return a 'KR-only' note, not crash."""
    db = db_for_tools
    stock = Stock(ticker="USTKR1", name="UsTicker", market="NASDAQ", sector="Tech")
    db.add(stock)
    await db.commit()
    out = await get_investor_flow("USTKR1")
    assert out.get("note") == "kr-only"


# --- get_macro_context ---

from datetime import date as _date  # noqa: E402

from app.models.macro_factor import MacroFactor  # noqa: E402
from app.services.analyst.tools import get_macro_context  # noqa: E402


@pytest.mark.asyncio
async def test_get_macro_context_returns_latest_per_factor(db_for_tools):
    db = db_for_tools
    db.add_all([
        MacroFactor(factor="VIX", date=_date(2026, 4, 28), value=18.7),
        MacroFactor(factor="VIX", date=_date(2026, 4, 27), value=19.2),
        MacroFactor(factor="USD/KRW", date=_date(2026, 4, 28), value=1378.0),
        MacroFactor(factor="US10Y", date=_date(2026, 4, 28), value=4.6),
    ])
    await db.commit()

    out = await get_macro_context()
    assert out["vix"] == 18.7  # latest only
    assert out["fx_pairs"]["USD/KRW"] == 1378.0
    assert out["us_10y"] == 4.6
    assert out["citations"][0]["source_type"] == "market_data"


import httpx as _httpx  # noqa: E402

from app.services.analyst.tools import web_search  # noqa: E402


@pytest.mark.asyncio
async def test_web_search_calls_tavily_and_returns_normalized(monkeypatch):
    fake_response = {
        "results": [
            {
                "title": "삼성전자 HBM3E 양산",
                "url": "https://example.com/news/1",
                "content": "삼성전자가 5월부터 HBM3E 양산을 시작한다.",
                "published_date": "2026-04-28",
            }
        ]
    }

    class _FakeR:
        status_code = 200

        def json(self):
            return fake_response

        def raise_for_status(self):
            pass

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, json):
            return _FakeR()

    monkeypatch.setattr(_httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(
        "app.services.analyst.tools.settings",
        type("S", (), {"tavily_api_key": "tvly-test"}),
    )

    out = await web_search("삼성전자 HBM3E", max_results=3)
    assert len(out["results"]) == 1
    assert out["results"][0]["url"] == "https://example.com/news/1"
    assert out["citations"][0]["source_type"] == "web"


@pytest.mark.asyncio
async def test_web_search_returns_empty_when_no_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyst.tools.settings",
        type("S", (), {"tavily_api_key": None}),
    )
    out = await web_search("anything")
    assert out["results"] == []
    assert out.get("error") == "tavily_api_key not set"


from unittest.mock import AsyncMock  # noqa: E402

from app.services.analyst.tools import (  # noqa: E402
    llm_classify_news,
    llm_discover_relations,
)


@pytest.mark.asyncio
async def test_llm_classify_news_returns_per_item_classification(monkeypatch):
    fake_response_text = (
        '{"items": ['
        '{"index": 0, "topic": "earnings", "sentiment": "positive", "impact": "positive"},'
        '{"index": 1, "topic": "macro", "sentiment": "negative", "impact": "negative"}'
        ']}'
    )

    fake_adapter = AsyncMock()
    fake_adapter.generate_json = AsyncMock(return_value=fake_response_text)
    monkeypatch.setattr(
        "app.services.analyst.tools._adapter", lambda: fake_adapter
    )

    items = [
        {"title": "1Q 어닝 서프라이즈", "summary": "..."},
        {"title": "Fed 매파 발언", "summary": "..."},
    ]
    out = await llm_classify_news(items)
    assert out["items"][0]["topic"] == "earnings"
    assert out["items"][1]["impact"] == "negative"


@pytest.mark.asyncio
async def test_llm_discover_relations_writes_to_cache(db_for_tools, monkeypatch):
    db = db_for_tools
    s = Stock(ticker="DSCV1", name="DSCV", market="KRX", sector="기타")
    db.add(s)
    await db.commit()

    fake_response_text = (
        '{"relations": ['
        '{"target_ticker": "DSCV2", "to_kind": "stock", "relation_type": "peer", "strength": 0.8, "notes": "동조"},'
        '{"target_ticker": "AI/HBM", "to_kind": "theme", "relation_type": "theme", "strength": 1.0}'
        ']}'
    )

    fake_adapter = AsyncMock()
    fake_adapter.generate_json = AsyncMock(return_value=fake_response_text)
    monkeypatch.setattr(
        "app.services.analyst.tools._adapter", lambda: fake_adapter
    )

    out = await llm_discover_relations("DSCV1", relation_types=["peer", "theme"])
    assert out["written"] >= 2
    rows = (
        await db.execute(
            select(StockRelation).where(StockRelation.from_stock_id == s.id)
        )
    ).scalars().all()
    assert len(rows) == 2
