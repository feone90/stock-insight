"""Dedup logic tests for the scheduler's unique-ticker selection."""
from datetime import date
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio

from app.models import Analysis, Favorite, Stock
from app.services.analyst.dedup import _parse_generated_at, unique_favorite_tickers


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


@pytest.mark.asyncio
async def test_unique_favorites_orders_missing_and_stale_cards_first(db_for_dedup):
    db = db_for_dedup
    missing = Stock(ticker="MISS1", name="missing", market="US", sector="x")
    stale = Stock(ticker="STALE1", name="stale", market="US", sector="x")
    fresh = Stock(ticker="FRESH1", name="fresh", market="US", sector="x")
    db.add_all([fresh, stale, missing])
    await db.flush()

    db.add_all([
        Favorite(user_id="u1", stock_id=fresh.id),
        Favorite(user_id="u1", stock_id=stale.id),
        Favorite(user_id="u1", stock_id=missing.id),
        Analysis(
            stock_id=fresh.id,
            date=date.today(),
            period_type="daily",
            summary="fresh",
            feedback="fresh",
            schema_version="v2",
            card_data={"generated_at": "2026-05-26T00:00:00Z"},
        ),
        Analysis(
            stock_id=stale.id,
            date=date.today(),
            period_type="daily",
            summary="stale",
            feedback="stale",
            schema_version="v2",
            card_data={"generated_at": "2026-05-22T00:00:00Z"},
        ),
    ])
    await db.commit()

    out = await unique_favorite_tickers(markets=["US"])

    assert out.index("MISS1") < out.index("STALE1") < out.index("FRESH1")


def test_parse_generated_at_handles_z_and_offset():
    assert _parse_generated_at("2026-05-26T00:00:00Z") == _parse_generated_at(
        "2026-05-26T00:00:00+00:00"
    )
    assert _parse_generated_at("not-a-date") is None
