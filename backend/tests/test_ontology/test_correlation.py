"""compute_pairwise_correlation + verify_inverse_signals — price-corr cases."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import PriceHistory, Stock, StockRelation
from app.services.ontology.correlation import (
    compute_pairwise_correlation,
    verify_inverse_signals,
)


def _seed_prices(db, stock: Stock, closes: list[float], end: date) -> None:
    """Append PriceHistory rows ending at `end`, walking backward by 1 day per close."""
    for offset, c in enumerate(reversed(closes)):
        d = end - timedelta(days=offset)
        db.add(PriceHistory(
            stock_id=stock.id, date=d,
            open=c, high=c, low=c, close=c, volume=1_000_000,
        ))


@pytest.mark.asyncio
async def test_correlation_strong_negative_for_anti_correlated_series(db) -> None:
    a = Stock(ticker="EX9201", name="A", market="US", sector="IT", tier=1)
    b = Stock(ticker="EX9202", name="B", market="US", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    end = date.today() - timedelta(days=1)
    # 40 close values where B moves opposite to A.
    a_closes = [100 + ((i % 5) - 2) * 2 for i in range(40)]
    b_closes = [100 - ((i % 5) - 2) * 2 for i in range(40)]
    _seed_prices(db, a, a_closes, end)
    _seed_prices(db, b, b_closes, end)
    await db.flush()

    corrs = await compute_pairwise_correlation(["EX9201", "EX9202"], session=db)
    pair = ("EX9201", "EX9202")
    assert pair in corrs
    assert corrs[pair] < -0.5  # strong inverse


@pytest.mark.asyncio
async def test_correlation_skips_short_series(db) -> None:
    a = Stock(ticker="EX9211", name="A", market="US", sector="IT", tier=1)
    b = Stock(ticker="EX9212", name="B", market="US", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    end = date.today() - timedelta(days=1)
    _seed_prices(db, a, [100.0, 101.0, 102.0], end)
    _seed_prices(db, b, [100.0, 99.0, 98.0], end)
    await db.flush()

    corrs = await compute_pairwise_correlation(["EX9211", "EX9212"], session=db)
    assert corrs == {}  # < _MIN_OBSERVATIONS=20


@pytest.mark.asyncio
async def test_verify_inverse_boosts_confidence_when_actually_inverse(db) -> None:
    a = Stock(ticker="EX9221", name="A", market="US", sector="IT", tier=1)
    b = Stock(ticker="EX9222", name="B", market="US", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    end = date.today() - timedelta(days=1)
    a_closes = [100 + ((i % 5) - 2) * 2 for i in range(40)]
    b_closes = [100 - ((i % 5) - 2) * 2 for i in range(40)]
    _seed_prices(db, a, a_closes, end)
    _seed_prices(db, b, b_closes, end)
    await db.flush()

    rel = StockRelation(
        from_stock_id=a.id, to_target=b.ticker, to_kind="stock",
        relation_type="competitor", signal_direction="inverse",
        strength=0.6, confidence=0.5, source="news",
    )
    db.add(rel)
    await db.flush()

    summary = await verify_inverse_signals(session=db)
    assert summary["boosted"] == 1
    assert summary["penalised"] == 0

    refreshed = (
        await db.execute(select(StockRelation).where(StockRelation.id == rel.id))
    ).scalar_one()
    assert refreshed.confidence == pytest.approx(0.6)  # +0.1


@pytest.mark.asyncio
async def test_verify_inverse_penalises_when_corr_is_positive(db) -> None:
    a = Stock(ticker="EX9231", name="A", market="US", sector="IT", tier=1)
    b = Stock(ticker="EX9232", name="B", market="US", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    end = date.today() - timedelta(days=1)
    # Both move together (positive correlation).
    closes = [100 + ((i % 5) - 2) * 2 for i in range(40)]
    _seed_prices(db, a, closes, end)
    _seed_prices(db, b, closes, end)
    await db.flush()

    rel = StockRelation(
        from_stock_id=a.id, to_target=b.ticker, to_kind="stock",
        relation_type="competitor", signal_direction="inverse",
        strength=0.6, confidence=0.7, source="news",
    )
    db.add(rel)
    await db.flush()

    summary = await verify_inverse_signals(session=db)
    assert summary["boosted"] == 0
    assert summary["penalised"] == 1

    refreshed = (
        await db.execute(select(StockRelation).where(StockRelation.id == rel.id))
    ).scalar_one()
    assert refreshed.confidence == pytest.approx(0.5)  # -0.2


@pytest.mark.asyncio
async def test_verify_inverse_skips_when_no_corr_data(db) -> None:
    a = Stock(ticker="EX9241", name="A", market="US", sector="IT", tier=1)
    b = Stock(ticker="EX9242", name="B", market="US", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    rel = StockRelation(
        from_stock_id=a.id, to_target=b.ticker, to_kind="stock",
        relation_type="competitor", signal_direction="inverse",
        strength=0.6, confidence=0.7, source="news",
    )
    db.add(rel)
    await db.flush()

    summary = await verify_inverse_signals(session=db)
    assert summary["skipped"] == 1
    assert summary["boosted"] == 0
    assert summary["penalised"] == 0
