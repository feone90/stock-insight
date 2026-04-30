"""validate_and_route — universe matching + dedup + buffer split."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import RelationCandidate, Stock, StockRelation
from app.services.ontology.schemas import ExtractedRelation
from app.services.ontology.validator import validate_and_route


def _rel(from_t: str, to_t: str, **overrides) -> ExtractedRelation:
    base = {
        "from_ticker": from_t,
        "to_ticker": to_t,
        "relation_type": "contract_supplier",
        "signal_direction": "positive",
        "strength": 0.7,
        "confidence": 0.8,
    }
    base.update(overrides)
    return ExtractedRelation.model_validate(base)


@pytest.mark.asyncio
async def test_both_sides_universe_persists_to_stock_relations(db) -> None:
    a = Stock(ticker="999801", name="A", market="KR", sector="IT", tier=1)
    b = Stock(ticker="999802", name="B", market="KR", sector="IT", tier=2)
    db.add_all([a, b])
    await db.flush()

    summary = await validate_and_route(
        [_rel("999801", "999802", confidence=0.9)],
        source="dart_contract",
        session=db,
    )

    # 1 forward + 1 reciprocal = 2 stock_relations rows
    assert summary["upserted"] == 2
    assert summary["buffered"] == 0

    forward = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.from_stock_id == a.id,
                StockRelation.source == "dart_contract",
            )
        )
    ).scalar_one()
    assert forward.to_target == "999802"
    assert forward.relation_type == "contract_supplier"

    reverse = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.from_stock_id == b.id,
                StockRelation.source == "dart_contract",
            )
        )
    ).scalar_one()
    assert reverse.to_target == "999801"
    # contract_supplier ↔ contract_customer
    assert reverse.relation_type == "contract_customer"


@pytest.mark.asyncio
async def test_one_side_only_buffered_in_candidates(db) -> None:
    a = Stock(ticker="999811", name="A", market="KR", sector="IT", tier=1)
    # other side absent from DB → buffered
    db.add(a)
    await db.flush()

    summary = await validate_and_route(
        [_rel("999811", "UNKNOWN_X")],
        source="dart_contract",
        session=db,
    )

    assert summary["upserted"] == 0
    assert summary["buffered"] == 1

    cands = (
        await db.execute(
            select(RelationCandidate).where(RelationCandidate.from_ticker == "999811")
        )
    ).scalars().all()
    assert len(cands) == 1
    assert cands[0].to_ticker == "UNKNOWN_X"
    assert cands[0].source == "dart_contract"


@pytest.mark.asyncio
async def test_tier_3_other_side_treated_as_outside_universe(db) -> None:
    """Universe = Tier 1+2. Tier 3 row exists but the relation goes to candidates."""
    a = Stock(ticker="999821", name="A", market="KR", sector="IT", tier=2)
    latent = Stock(ticker="999822", name="L", market="KR", sector="IT", tier=3)
    db.add_all([a, latent])
    await db.flush()

    summary = await validate_and_route(
        [_rel("999821", "999822")], source="dart_contract", session=db
    )

    assert summary["upserted"] == 0
    assert summary["buffered"] == 1


@pytest.mark.asyncio
async def test_dedup_within_batch_keeps_higher_confidence(db) -> None:
    a = Stock(ticker="999831", name="A", market="KR", sector="IT", tier=1)
    b = Stock(ticker="999832", name="B", market="KR", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    # Two identical edges, second has higher confidence — second wins.
    summary = await validate_and_route(
        [
            _rel("999831", "999832", confidence=0.6, strength=0.4),
            _rel("999831", "999832", confidence=0.9, strength=0.7),
        ],
        source="dart_contract",
        session=db,
    )

    assert summary["received"] == 2
    assert summary["deduped"] == 1
    assert summary["upserted"] == 2  # forward + reciprocal

    rel = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.from_stock_id == a.id,
                StockRelation.source == "dart_contract",
            )
        )
    ).scalar_one()
    assert rel.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_self_loop_dropped(db) -> None:
    a = Stock(ticker="999841", name="A", market="KR", sector="IT", tier=1)
    db.add(a)
    await db.flush()

    summary = await validate_and_route(
        [_rel("999841", "999841")], source="dart_contract", session=db
    )

    assert summary["self_loop_dropped"] == 1
    assert summary["upserted"] == 0
    assert summary["buffered"] == 0


@pytest.mark.asyncio
async def test_low_confidence_dropped(db) -> None:
    a = Stock(ticker="999851", name="A", market="KR", sector="IT", tier=1)
    b = Stock(ticker="999852", name="B", market="KR", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    summary = await validate_and_route(
        [_rel("999851", "999852", confidence=0.1)],  # below floor 0.3
        source="dart_contract",
        session=db,
    )

    assert summary["low_conf_dropped"] == 1
    assert summary["upserted"] == 0
    assert summary["buffered"] == 0


@pytest.mark.asyncio
async def test_mid_confidence_flagged_for_review_but_persisted(db) -> None:
    a = Stock(ticker="999861", name="A", market="KR", sector="IT", tier=1)
    b = Stock(ticker="999862", name="B", market="KR", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    # 0.3 ≤ confidence < 0.6 → metadata.needs_review = True, but row persisted.
    await validate_and_route(
        [_rel("999861", "999862", confidence=0.5)],
        source="dart_contract",
        session=db,
    )

    rel = (
        await db.execute(
            select(StockRelation).where(StockRelation.from_stock_id == a.id)
        )
    ).scalar_one()
    assert rel.extra_metadata is not None
    assert rel.extra_metadata.get("needs_review") is True
