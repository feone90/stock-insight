"""promote_to_tier_2 — tier 3 → 2 자동 승격 + idempotency."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.models import Stock
from app.services.universe import tier_promotion


@asynccontextmanager
async def _patched_session(db):
    """Yield the same per-test session that tier_promotion would otherwise open
    via `async_session()`. Keeps writes inside the test transaction."""
    yield db


@pytest.mark.asyncio
async def test_promote_tier_3_to_2_with_user_promoted_source(db, monkeypatch) -> None:
    stock = Stock(ticker="999801", name="Latent", market="KR", sector="IT", tier=3)
    db.add(stock)
    await db.flush()

    monkeypatch.setattr(tier_promotion, "async_session", lambda: _patched_session(db))
    await tier_promotion.promote_to_tier_2(stock.id)

    refreshed = (await db.execute(select(Stock).where(Stock.id == stock.id))).scalar_one()
    assert refreshed.tier == 2
    assert refreshed.universe_source == "user_promoted"
    assert refreshed.tier_updated_at is not None


@pytest.mark.asyncio
async def test_promote_noop_for_tier_2_already(db, monkeypatch) -> None:
    stock = Stock(
        ticker="999802",
        name="Touched",
        market="KR",
        sector="IT",
        tier=2,
        universe_source="seed_legacy",
    )
    db.add(stock)
    await db.flush()

    monkeypatch.setattr(tier_promotion, "async_session", lambda: _patched_session(db))
    await tier_promotion.promote_to_tier_2(stock.id)

    refreshed = (await db.execute(select(Stock).where(Stock.id == stock.id))).scalar_one()
    assert refreshed.tier == 2
    # User-touched source preserved — promote did not overwrite.
    assert refreshed.universe_source == "seed_legacy"


@pytest.mark.asyncio
async def test_promote_noop_for_tier_1_reference(db, monkeypatch) -> None:
    stock = Stock(
        ticker="999803",
        name="Reference",
        market="KR",
        sector="IT",
        tier=1,
        universe_source="kospi_listing",
    )
    db.add(stock)
    await db.flush()

    monkeypatch.setattr(tier_promotion, "async_session", lambda: _patched_session(db))
    await tier_promotion.promote_to_tier_2(stock.id)

    refreshed = (await db.execute(select(Stock).where(Stock.id == stock.id))).scalar_one()
    # Reference tier preserved (tier 1 is "stronger" than user-touched).
    assert refreshed.tier == 1
    assert refreshed.universe_source == "kospi_listing"
