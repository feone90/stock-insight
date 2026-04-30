"""scan_pending_candidates — Tier 3 buffer → stock_relations promotion."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import RelationCandidate, Stock, StockRelation
from app.services.ontology import upsert as upsert_module


@pytest.mark.asyncio
async def test_promote_when_both_sides_in_universe(db) -> None:
    a = Stock(ticker="999601", name="A", market="KR", sector="IT", tier=2)
    b = Stock(ticker="999602", name="B", market="KR", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    cand = RelationCandidate(
        from_ticker="999601",
        to_ticker="999602",
        relation_type="contract_supplier",
        signal_direction="positive",
        strength=0.7,
        confidence=0.9,
        source="dart_contract",
        source_url="https://dart.fss.or.kr/sample",
    )
    db.add(cand)
    await db.flush()

    promoted = await upsert_module.scan_pending_candidates(a.id, session=db)
    assert promoted == 1

    refreshed_cand = (
        await db.execute(select(RelationCandidate).where(RelationCandidate.id == cand.id))
    ).scalar_one()
    assert refreshed_cand.promoted_at is not None
    assert refreshed_cand.promoted_to_relation_id is not None

    relation = (
        await db.execute(
            select(StockRelation).where(StockRelation.id == refreshed_cand.promoted_to_relation_id)
        )
    ).scalar_one()
    assert relation.from_stock_id == a.id
    assert relation.to_target == "999602"
    assert relation.relation_type == "contract_supplier"
    assert relation.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_buffered_when_other_side_still_tier_3(db) -> None:
    a = Stock(ticker="999611", name="A", market="KR", sector="IT", tier=2)
    other = Stock(ticker="999612", name="Other", market="KR", sector="IT", tier=3)
    db.add_all([a, other])
    await db.flush()

    cand = RelationCandidate(
        from_ticker="999611",
        to_ticker="999612",
        relation_type="competitor",
        signal_direction="inverse",
        strength=0.6,
        confidence=0.7,
        source="news_extraction",
    )
    db.add(cand)
    await db.flush()

    promoted = await upsert_module.scan_pending_candidates(a.id, session=db)
    assert promoted == 0  # other side still latent — keep buffered

    refreshed_cand = (
        await db.execute(select(RelationCandidate).where(RelationCandidate.id == cand.id))
    ).scalar_one()
    assert refreshed_cand.promoted_at is None


@pytest.mark.asyncio
async def test_already_promoted_candidates_are_skipped(db) -> None:
    from datetime import datetime

    a = Stock(ticker="999621", name="A", market="KR", sector="IT", tier=2)
    b = Stock(ticker="999622", name="B", market="KR", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    already = RelationCandidate(
        from_ticker="999621",
        to_ticker="999622",
        relation_type="peer",
        signal_direction="positive",
        strength=0.5,
        confidence=0.5,
        source="legacy",
        promoted_at=datetime(2026, 1, 1),
    )
    fresh = RelationCandidate(
        from_ticker="999621",
        to_ticker="999622",
        relation_type="contract_customer",
        signal_direction="positive",
        strength=0.6,
        confidence=0.8,
        source="dart_contract",
    )
    db.add_all([already, fresh])
    await db.flush()

    promoted = await upsert_module.scan_pending_candidates(a.id, session=db)
    assert promoted == 1  # only the fresh one moved

    refreshed_already = (
        await db.execute(select(RelationCandidate).where(RelationCandidate.id == already.id))
    ).scalar_one()
    assert refreshed_already.promoted_at == datetime(2026, 1, 1)  # unchanged

    refreshed_fresh = (
        await db.execute(select(RelationCandidate).where(RelationCandidate.id == fresh.id))
    ).scalar_one()
    assert refreshed_fresh.promoted_at is not None
