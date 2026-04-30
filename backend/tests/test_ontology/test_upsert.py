"""bulk_upsert_relations — ON CONFLICT DO UPDATE invariants."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Stock, StockRelation
from app.services.ontology import upsert as upsert_module


def _row(from_id: int, to_ticker: str, **overrides) -> dict:
    base = {
        "from_stock_id": from_id,
        "to_target": to_ticker,
        "to_kind": "stock",
        "relation_type": "peer",
        "strength": 0.5,
        "source": "sector_match",
        "signal_direction": "positive",
        "confidence": 0.4,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_upsert_same_quad_averages_strength_max_confidence(db) -> None:
    a = Stock(ticker="999501", name="A", market="KR", sector="IT")
    b = Stock(ticker="999502", name="B", market="KR", sector="IT")
    db.add_all([a, b])
    await db.flush()

    # First upsert: strength=0.6, confidence=0.4
    await upsert_module.bulk_upsert_relations(
        [_row(a.id, b.ticker, strength=0.6, confidence=0.4)], session=db
    )
    # Second upsert: strength=0.4, confidence=0.7 — same (from, to, type, source)
    await upsert_module.bulk_upsert_relations(
        [_row(a.id, b.ticker, strength=0.4, confidence=0.7)], session=db
    )

    rows = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.from_stock_id == a.id,
                StockRelation.to_target == b.ticker,
                StockRelation.source == "sector_match",
            )
        )
    ).scalars().all()

    assert len(rows) == 1  # ON CONFLICT collapsed to one row
    edge = rows[0]
    assert edge.strength == pytest.approx(0.5)  # (0.6 + 0.4) / 2
    assert edge.confidence == pytest.approx(0.7)  # MAX(0.4, 0.7)


@pytest.mark.asyncio
async def test_upsert_different_source_keeps_separate_rows(db) -> None:
    a = Stock(ticker="999511", name="A", market="KR", sector="IT")
    b = Stock(ticker="999512", name="B", market="KR", sector="IT")
    db.add_all([a, b])
    await db.flush()

    await upsert_module.bulk_upsert_relations(
        [
            _row(a.id, b.ticker, source="sector_match"),
            _row(a.id, b.ticker, source="dart_contract"),
        ],
        session=db,
    )

    rows = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.from_stock_id == a.id,
                StockRelation.to_target == b.ticker,
            )
        )
    ).scalars().all()
    sources = {r.source for r in rows}
    assert sources == {"sector_match", "dart_contract"}


@pytest.mark.asyncio
async def test_upsert_bidirectional_persists_two_rows(db) -> None:
    a = Stock(ticker="999521", name="A", market="KR", sector="IT")
    b = Stock(ticker="999522", name="B", market="KR", sector="IT")
    db.add_all([a, b])
    await db.flush()

    await upsert_module.bulk_upsert_relations(
        [_row(a.id, b.ticker), _row(b.id, a.ticker)], session=db
    )

    rows = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.source == "sector_match",
                StockRelation.from_stock_id.in_([a.id, b.id]),
            )
        )
    ).scalars().all()
    assert len(rows) == 2
    pairs = {(r.from_stock_id, r.to_target) for r in rows}
    assert (a.id, b.ticker) in pairs
    assert (b.id, a.ticker) in pairs
