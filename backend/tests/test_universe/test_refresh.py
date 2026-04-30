"""nightly_universe_refresh — fetch + upsert + dropout demote."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models import Stock
from app.services.universe import refresh as refresh_module
from app.services.universe import upsert as upsert_module
from app.services.universe.types import UniverseRow


@asynccontextmanager
async def _patched_session(db):
    yield db


def _row(ticker: str, sector: str = "IT", source: str = "kospi_listing") -> UniverseRow:
    return UniverseRow(
        ticker=ticker,
        name=f"Name-{ticker}",
        market="KOSPI" if source.startswith("kospi") else "US",
        sector=sector,
        industry_group=None,
        listing_date=None,
        universe_source=source,
    )


@pytest.mark.asyncio
async def test_refresh_promotes_new_entrants_and_preserves_user_touched(
    db, monkeypatch
) -> None:
    """Existing tier-2 user-touched row stays at tier 2; new fetch row enters as tier 1."""
    existing = Stock(
        ticker="999701",
        name="UserTouched",
        market="KR",
        sector="IT",
        tier=2,
        universe_source="seed_legacy",
    )
    db.add(existing)
    await db.flush()

    fresh = [
        _row("999701"),  # already exists at tier 2 → must stay tier 2
        _row("999702"),  # net new → tier 1
    ]

    monkeypatch.setattr(
        refresh_module, "fetch_kr_universe", AsyncMock(return_value=fresh)
    )
    monkeypatch.setattr(refresh_module, "fetch_us_universe", AsyncMock(return_value=[]))
    monkeypatch.setattr(upsert_module, "async_session", lambda: _patched_session(db))
    monkeypatch.setattr(refresh_module, "async_session", lambda: _patched_session(db))

    summary = await refresh_module.nightly_universe_refresh()
    db.expire_all()  # ORM cache flush — pick up commits made by bulk_upsert.

    assert summary["upserted"] == 2

    rows = (
        await db.execute(select(Stock).where(Stock.ticker.in_(["999701", "999702"])))
    ).scalars().all()
    by_ticker = {r.ticker: r for r in rows}

    assert by_ticker["999701"].tier == 2  # CASE clause preserved user-touched
    assert by_ticker["999701"].universe_source == "kospi_listing"  # source refreshed
    assert by_ticker["999702"].tier == 1


@pytest.mark.asyncio
async def test_refresh_demotes_auto_source_dropouts(db, monkeypatch) -> None:
    """Tier-1 row from auto fetch source falls out of fresh universe → demote to tier 2."""
    dropout = Stock(
        ticker="999710",
        name="Dropout",
        market="KOSPI",
        sector="IT",
        tier=1,
        universe_source="kospi_listing",
    )
    survivor = Stock(
        ticker="999711",
        name="Survivor",
        market="KOSPI",
        sector="IT",
        tier=1,
        universe_source="kospi_listing",
    )
    user_locked = Stock(
        ticker="999712",
        name="UserLocked",
        market="KOSPI",
        sector="IT",
        tier=1,
        universe_source="user_promoted",  # protected from demote
    )
    db.add_all([dropout, survivor, user_locked])
    await db.flush()

    fresh = [_row("999711")]  # only survivor in fresh universe

    monkeypatch.setattr(
        refresh_module, "fetch_kr_universe", AsyncMock(return_value=fresh)
    )
    monkeypatch.setattr(refresh_module, "fetch_us_universe", AsyncMock(return_value=[]))
    monkeypatch.setattr(upsert_module, "async_session", lambda: _patched_session(db))
    monkeypatch.setattr(refresh_module, "async_session", lambda: _patched_session(db))

    summary = await refresh_module.nightly_universe_refresh()
    db.expire_all()

    assert summary["demoted"] == 1  # only the auto-source dropout
    rows = (
        await db.execute(
            select(Stock).where(Stock.ticker.in_(["999710", "999711", "999712"]))
        )
    ).scalars().all()
    by_ticker = {r.ticker: r for r in rows}

    assert by_ticker["999710"].tier == 2
    assert by_ticker["999710"].universe_source == "demoted_dropout"
    assert by_ticker["999711"].tier == 1  # survivor preserved
    assert by_ticker["999712"].tier == 1  # user_promoted protected
    assert by_ticker["999712"].universe_source == "user_promoted"


@pytest.mark.asyncio
async def test_refresh_skips_when_both_fetches_fail(db, monkeypatch) -> None:
    """Empty fetch must short-circuit — never mass-demote."""
    existing = Stock(
        ticker="999720",
        name="Existing",
        market="KOSPI",
        sector="IT",
        tier=1,
        universe_source="kospi_listing",
    )
    db.add(existing)
    await db.flush()

    monkeypatch.setattr(refresh_module, "fetch_kr_universe", AsyncMock(return_value=[]))
    monkeypatch.setattr(refresh_module, "fetch_us_universe", AsyncMock(return_value=[]))
    monkeypatch.setattr(upsert_module, "async_session", lambda: _patched_session(db))
    monkeypatch.setattr(refresh_module, "async_session", lambda: _patched_session(db))

    summary = await refresh_module.nightly_universe_refresh()
    await db.flush()

    assert summary == {"fetched": 0, "upserted": 0, "demoted": 0}
    refreshed = (
        await db.execute(select(Stock).where(Stock.ticker == "999720"))
    ).scalar_one()
    assert refreshed.tier == 1  # not touched
