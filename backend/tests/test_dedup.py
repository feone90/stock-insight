"""Dedup logic tests for the scheduler's unique-ticker selection."""
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio

from app.models import Favorite, Stock
from app.services.analyst.dedup import unique_favorite_tickers


@pytest_asyncio.fixture
async def db_for_dedup(db, monkeypatch):
    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("app.services.analyst.dedup.async_session", _session)
    return db


@pytest.mark.asyncio
async def test_unique_favorites_dedups_across_users(db_for_dedup):
    db = db_for_dedup
    s1 = Stock(ticker="DUP1", name="d1", market="KRX", sector="x")
    s2 = Stock(ticker="DUP2", name="d2", market="KRX", sector="x")
    db.add_all([s1, s2])
    await db.flush()

    db.add_all([
        Favorite(user_id="u1", stock_id=s1.id),
        Favorite(user_id="u2", stock_id=s1.id),  # dup
        Favorite(user_id="u3", stock_id=s2.id),
    ])
    await db.commit()

    out = await unique_favorite_tickers()
    assert "DUP1" in out
    assert "DUP2" in out
    # No duplicates
    assert out.count("DUP1") == 1


@pytest.mark.asyncio
async def test_unique_favorites_filters_by_market(db_for_dedup):
    db = db_for_dedup
    s = Stock(ticker="USONLY", name="us", market="NASDAQ", sector="Tech")
    db.add(s)
    await db.flush()
    db.add(Favorite(user_id="u1", stock_id=s.id))
    await db.commit()

    kr_only = await unique_favorite_tickers(markets=["KOSPI", "KOSDAQ", "KRX"])
    assert "USONLY" not in kr_only

    us_only = await unique_favorite_tickers(markets=["NASDAQ", "NYSE"])
    assert "USONLY" in us_only
