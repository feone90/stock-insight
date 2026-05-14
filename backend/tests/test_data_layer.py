"""Data layer tests — `assemble_data_layer` aggregates 5 deterministic fetches.

Most cases mock the individual sub-fetches because the test fixture shares a
single AsyncSession across the gather (production opens fresh sessions per
fetch from the connection pool, so concurrent ops never collide there).
Direct-DB cases use a single sequential call.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.models import News, Stock
from app.models.relation import StockRelation
from app.schemas.card import DataLayer
from app.services.analyst.data_layer import (
    _CitationPool,
    _fetch_recent_news,
    _fetch_relations_data,
    assemble_data_layer,
    fetch_stock_identity,
)


@pytest_asyncio.fixture
async def db_for_data_layer(db, monkeypatch):
    """Share the test session for direct-DB helper tests (sequential calls)."""

    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("app.services.analyst.data_layer.async_session", _session)
    return db


def _full_indicators_response() -> dict:
    return {
        "rsi_14": 58.0, "atr_pct": 2.0, "ma_stack": "정배열",
        "rvol_20": 1.4, "obv_ratio": 1.0, "cmf_20": 0.05,
        "citations": [{"source_type": "db", "label": "DB · price_history"}],
    }


def _full_macro_response() -> dict:
    return {
        "vix": 18.7, "us_10y": 4.6,
        "fx_pairs": {"USD/KRW": 1378.0},
        "upcoming_events": [],
        "citations": [{"source_type": "market_data", "label": "DB · macro_factors"}],
    }


def _full_fundamentals_response() -> dict:
    return {
        "per": 12.0, "pbr": 1.1,
        "market_cap_krw": 1e12, "dividend_yield": 2.0,
        "label": "DB · financials (2026Q1)",
    }


def _full_news_response() -> dict:
    return {
        "items": [
            {
                "title": "HBM3E 양산", "source": "조선",
                "url": "https://example.com/n/1",
                "published_at": datetime.utcnow() - timedelta(days=1),
                "summary": "ok",
            }
        ]
    }


def _full_relations_response(is_stale: bool = False) -> dict:
    return {
        "relations": [
            {
                "target_ticker": "000660", "target_name": "SK하이닉스",
                "relation_type": "peer", "strength": 0.9, "today_change_pct": 2.8,
            }
        ],
        "is_stale": is_stale,
    }


def _patch_all_fetches(
    monkeypatch,
    *,
    indicators=None,
    macro=None,
    fundamentals=None,
    news=None,
    relations=None,
    classify=None,
):
    monkeypatch.setattr(
        "app.services.analyst.data_layer.get_indicators",
        AsyncMock(return_value=indicators if indicators is not None else _full_indicators_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer.get_macro_context",
        AsyncMock(return_value=macro if macro is not None else _full_macro_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._fetch_fundamentals",
        AsyncMock(return_value=fundamentals if fundamentals is not None else _full_fundamentals_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._fetch_recent_news",
        AsyncMock(return_value=news if news is not None else _full_news_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._fetch_relations_data",
        AsyncMock(return_value=relations if relations is not None else _full_relations_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value=classify if classify is not None else {"items": []}),
    )


@pytest.mark.asyncio
async def test_assemble_returns_full_data_layer(monkeypatch):
    _patch_all_fetches(monkeypatch)
    out = await assemble_data_layer("DL1")
    assert isinstance(out, DataLayer)
    assert out.technical is not None and out.technical.rsi_14 == 58.0
    assert out.macro is not None and out.macro.us_10y == 4.6
    assert out.fundamentals is not None and out.fundamentals.per == 12.0
    assert len(out.news) == 1
    assert out.news[0].impact == "neutral"
    assert len(out.relations_data) == 1
    assert out.relations_data[0].target_ticker == "000660"
    citation_ids = [c.id for c in out.data_citations]
    assert citation_ids == list(range(1, len(citation_ids) + 1))  # 1..K contiguous


@pytest.mark.asyncio
async def test_assemble_handles_missing_indicators_gracefully(monkeypatch):
    """< 30 days price history → indicators returns error → technical=None."""
    _patch_all_fetches(monkeypatch, indicators={"error": "insufficient data"})
    out = await assemble_data_layer("DL2")
    assert out.technical is None
    assert out.macro is not None  # other sections still populated
    assert out.fundamentals is not None


@pytest.mark.asyncio
async def test_assemble_handles_empty_news(monkeypatch):
    _patch_all_fetches(monkeypatch, news={"items": []})
    out = await assemble_data_layer("DL3")
    assert out.news == []


@pytest.mark.asyncio
async def test_assemble_handles_empty_macro(monkeypatch):
    _patch_all_fetches(monkeypatch, macro={"vix": None, "fx_pairs": {}, "citations": []})
    out = await assemble_data_layer("DL4")
    assert out.macro is None


@pytest.mark.asyncio
async def test_assemble_handles_indicator_exception(monkeypatch):
    """If a sub-fetch raises, the whole assemble must not raise."""
    async def boom(_ticker):
        raise RuntimeError("upstream blew up")

    _patch_all_fetches(monkeypatch)
    monkeypatch.setattr("app.services.analyst.data_layer.get_indicators", boom)
    out = await assemble_data_layer("DL5")
    assert out.technical is None  # graceful degrade
    assert out.macro is not None  # rest unaffected


@pytest.mark.asyncio
async def test_assemble_classifies_news_impact(monkeypatch):
    classify_response = {
        "items": [
            {"index": 0, "topic": "earnings", "sentiment": "positive", "impact": "positive"}
        ]
    }
    _patch_all_fetches(monkeypatch, classify=classify_response)
    out = await assemble_data_layer("DL6")
    assert out.news[0].impact == "positive"


@pytest.mark.asyncio
async def test_assemble_uses_asyncio_gather(monkeypatch):
    """All 5 fetches run concurrently."""
    delay = 0.05

    async def slow(*args, **kwargs):
        await asyncio.sleep(delay)
        return {}

    async def slow_indicators(_ticker):
        await asyncio.sleep(delay)
        return {"error": "no data"}

    async def slow_macro():
        await asyncio.sleep(delay)
        return {}

    monkeypatch.setattr("app.services.analyst.data_layer.get_indicators", slow_indicators)
    monkeypatch.setattr("app.services.analyst.data_layer.get_macro_context", slow_macro)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_fundamentals", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_recent_news", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_relations_data", slow)
    # 2026-05-14 — 추가된 새 fetcher 6 개도 monkeypatch (concurrent 검증 fair).
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_political_signals", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_flow", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_insider", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_earnings", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_analyst_rating", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_price_target", slow)
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value={"items": []}),
    )

    start = asyncio.get_event_loop().time()
    await assemble_data_layer("DL7")
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < delay * 3, f"expected gather (<~{delay*3}s), got {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_assemble_triggers_bg_refresh_when_relations_stale(monkeypatch):
    bg_called: list[str] = []

    async def fake_bg(ticker: str) -> None:
        bg_called.append(ticker)

    _patch_all_fetches(monkeypatch, relations=_full_relations_response(is_stale=True))
    monkeypatch.setattr("app.services.analyst.data_layer._bg_refresh_relations", fake_bg)

    await assemble_data_layer("DL8")
    # Yield to event loop so the fire-and-forget task runs
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert "DL8" in bg_called


@pytest.mark.asyncio
async def test_assemble_skips_bg_refresh_when_relations_fresh(monkeypatch):
    bg_called: list[str] = []

    async def fake_bg(ticker: str) -> None:
        bg_called.append(ticker)

    _patch_all_fetches(monkeypatch, relations=_full_relations_response(is_stale=False))
    monkeypatch.setattr("app.services.analyst.data_layer._bg_refresh_relations", fake_bg)

    await assemble_data_layer("DL9")
    await asyncio.sleep(0)
    assert bg_called == []


# ---------------------------------------------------------------------------
# Direct DB helpers — single sequential call, safe with shared session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_recent_news_filters_older_than_14_days(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(ticker="NW1", name="x", market="KRX", sector="x", current_price=10)
    db.add(s)
    await db.flush()
    db.add_all([
        News(
            stock_id=s.id, title="recent", source="src",
            url="https://e.com/recent",
            published_at=datetime.utcnow() - timedelta(days=2),
            content="recent",
        ),
        News(
            stock_id=s.id, title="too old", source="src",
            url="https://e.com/old",
            published_at=datetime.utcnow() - timedelta(days=30),
            content="too old",
        ),
    ])
    await db.commit()

    res = await _fetch_recent_news("NW1")
    titles = [it["title"] for it in res["items"]]
    assert "recent" in titles
    assert "too old" not in titles


@pytest.mark.asyncio
async def test_fetch_relations_data_detects_stale(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(ticker="RL1", name="x", market="KRX", sector="x", current_price=10)
    db.add(s)
    await db.flush()
    db.add(
        StockRelation(
            from_stock_id=s.id, to_target="000660", to_kind="stock",
            relation_type="peer", strength=0.8,
            refreshed_at=datetime.utcnow() - timedelta(days=10),
        )
    )
    await db.commit()
    res = await _fetch_relations_data("RL1")
    assert res["is_stale"] is True
    assert len(res["relations"]) == 1


@pytest.mark.asyncio
async def test_fetch_stock_identity_returns_db_fields(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(
        ticker="ID1", name="아이덴티티", market="KRX", sector="반도체",
        current_price=88.5, change=1.2, change_percent=1.4,
    )
    db.add(s)
    await db.commit()
    out = await fetch_stock_identity("ID1")
    assert out["ticker"] == "ID1"
    assert out["name_ko"] == "아이덴티티"
    assert out["sector"] == "반도체"
    assert out["price"] == 88.5
    assert isinstance(out["asof"], datetime)


def test_citation_pool_assigns_sequential_ids():
    p = _CitationPool()
    a = p.add("db", "alpha")
    b = p.add("news", "beta", url="https://example.com")
    c = p.add("web", "gamma")
    assert (a, b, c) == (1, 2, 3)
    assert [item.id for item in p.items] == [1, 2, 3]
    assert p.items[1].url == "https://example.com"
