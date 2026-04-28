"""v2 card API endpoint tests.

After the data/analyst split, `/analyze` and `/refresh` perform a fail-fast
`is_analyzable` check at API level — stocks with `current_price <= 0` or
no price history return 422.
"""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.models import Stock
from app.models.analysis import Analysis


def _seed_analyzable_stock(db, ticker: str) -> Stock:
    """Stock with price > 0 + 1 history row → passes is_analyzable."""
    s = Stock(ticker=ticker, name="x", market="KRX", sector="x", current_price=100.0)
    db.add(s)
    return s


@pytest.mark.asyncio
async def test_get_card_404_when_no_analysis(client, db):
    s = Stock(ticker="EMPTY1", name="empty", market="KRX", sector="x")
    db.add(s)
    await db.commit()

    resp = await client.get("/api/stocks/EMPTY1/card")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_card_returns_v2_card(client, db):
    s = Stock(ticker="HASCARD", name="x", market="KRX", sector="x")
    db.add(s)
    await db.flush()
    db.add(
        Analysis(
            stock_id=s.id,
            date=date.today(),
            period_type="daily",
            summary="x",
            feedback="x",
            schema_version="v2",
            card_data={
                "ticker": "HASCARD",
                "name_ko": "x",
                "glance": {"final_grade": "B", "stance": "WATCH"},
            },
            persona_version="analyst_v1",
        )
    )
    await db.commit()

    resp = await client.get("/api/stocks/HASCARD/card")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "HASCARD"
    assert body["glance"]["stance"] == "WATCH"


@pytest.mark.asyncio
async def test_get_card_skips_v1_rows(client, db):
    """Phase A v1 rows must NOT be returned by the v2 endpoint."""
    s = Stock(ticker="ONLYV1", name="x", market="KRX", sector="x")
    db.add(s)
    await db.flush()
    db.add(
        Analysis(
            stock_id=s.id,
            date=date.today(),
            period_type="daily",
            summary="x",
            feedback="x",
            schema_version="v1",
        )
    )
    await db.commit()

    resp = await client.get("/api/stocks/ONLYV1/card")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyze_endpoint_queues_engine(client, db, monkeypatch):
    _seed_analyzable_stock(db, "ANAL1")
    await db.commit()

    monkeypatch.setattr(
        "app.api.cards.analyze", AsyncMock(return_value=None)
    )
    # `is_analyzable` opens its own session; bypass for queue test
    monkeypatch.setattr(
        "app.api.cards.is_analyzable", AsyncMock(return_value=(True, None))
    )

    resp = await client.post("/api/stocks/ANAL1/analyze")
    assert resp.status_code == 202
    assert resp.json()["ticker"] == "ANAL1"


@pytest.mark.asyncio
async def test_analyze_returns_422_when_price_zero(client, db, monkeypatch):
    """Spec §6 — API surfaces is_analyzable's 'no usable price' as 422."""
    s = Stock(ticker="ZEROPRICE", name="x", market="KRX", sector="x", current_price=0)
    db.add(s)
    await db.commit()
    monkeypatch.setattr(
        "app.api.cards.is_analyzable",
        AsyncMock(return_value=(False, "current_price <= 0")),
    )

    resp = await client.post("/api/stocks/ZEROPRICE/analyze")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analyze_returns_422_when_no_price_history(client, db, monkeypatch):
    _seed_analyzable_stock(db, "NOHIST")
    await db.commit()
    monkeypatch.setattr(
        "app.api.cards.is_analyzable",
        AsyncMock(return_value=(False, "no price history")),
    )

    resp = await client.post("/api/stocks/NOHIST/analyze")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_refresh_blocked_by_cooldown(client, db, monkeypatch):
    _seed_analyzable_stock(db, "COOL")
    await db.commit()

    monkeypatch.setattr(
        "app.api.cards.analyze", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "app.api.cards.is_analyzable", AsyncMock(return_value=(True, None))
    )
    monkeypatch.setattr("app.api.cards._last_refresh", {})

    r1 = await client.post("/api/stocks/COOL/refresh")
    assert r1.status_code == 202
    r2 = await client.post("/api/stocks/COOL/refresh")
    assert r2.status_code == 429


@pytest.mark.asyncio
async def test_analyze_blocked_by_kill_switch(client, db, monkeypatch):
    _seed_analyzable_stock(db, "KILL")
    await db.commit()

    monkeypatch.setattr("app.api.cards.can_proceed", lambda: False)

    resp = await client.post("/api/stocks/KILL/analyze")
    assert resp.status_code == 503
