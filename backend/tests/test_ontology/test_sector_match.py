"""universe_wide_sector_match — bidirectional cross-match cases."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Stock, StockRelation
from app.services.ontology import sector_match


def _stock(ticker: str, sector: str, **kwargs) -> Stock:
    return Stock(
        ticker=ticker,
        name=f"Name-{ticker}",
        market="KOSPI",
        sector=sector,
        tier=kwargs.pop("tier", 1),
        is_delisted=kwargs.pop("is_delisted", False),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_sector_match_emits_bidirectional_peers(db) -> None:
    a = _stock("999401", "Tech")
    b = _stock("999402", "Tech")
    c = _stock("999403", "Tech")
    db.add_all([a, b, c])
    await db.flush()

    summary = await sector_match.universe_wide_sector_match(session=db)

    # C(3,2) × 2 = 6 directed peer rows
    assert summary["pair_rows"] == 6
    assert summary["upserted"] == 6

    relations = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.from_stock_id.in_([a.id, b.id, c.id]),
                StockRelation.source == "sector_match",
            )
        )
    ).scalars().all()
    pairs = {(r.from_stock_id, r.to_target) for r in relations}

    # Both directions for every pair
    assert (a.id, "999402") in pairs
    assert (b.id, "999401") in pairs
    assert (a.id, "999403") in pairs
    assert (c.id, "999401") in pairs
    assert (b.id, "999403") in pairs
    assert (c.id, "999402") in pairs


@pytest.mark.asyncio
async def test_sector_match_caps_oversized_sector(db) -> None:
    """Sector with > SECTOR_PAIR_CAP members keeps only the top-N to bound explosion."""
    cap = sector_match.SECTOR_PAIR_CAP
    members = [_stock(f"99{i:04d}", "BigSector") for i in range(cap + 5)]
    db.add_all(members)
    await db.flush()

    summary = await sector_match.universe_wide_sector_match(session=db)

    expected_pairs = cap * (cap - 1)  # C(cap, 2) × 2 (bidirectional)
    assert summary["pair_rows"] == expected_pairs
    assert summary["sectors_capped"] == 1


@pytest.mark.asyncio
async def test_sector_match_skips_unknown_and_singleton(db) -> None:
    db.add_all([
        _stock("999411", "Unknown"),
        _stock("999412", "Unknown"),
        _stock("999413", "SoloSector"),  # only one in this sector — no pairs
    ])
    await db.flush()

    summary = await sector_match.universe_wide_sector_match(session=db)

    assert summary["pair_rows"] == 0
    assert summary["upserted"] == 0


@pytest.mark.asyncio
async def test_sector_match_excludes_tier_3_and_delisted(db) -> None:
    db.add_all([
        _stock("999421", "Mixed", tier=1),
        _stock("999422", "Mixed", tier=2),
        _stock("999423", "Mixed", tier=3),  # latent — excluded
        _stock("999424", "Mixed", tier=1, is_delisted=True),  # excluded
    ])
    await db.flush()

    summary = await sector_match.universe_wide_sector_match(session=db)

    # Only tier 1 + 2 → 2 active members → C(2,2) × 2 = 2 directed rows
    assert summary["pair_rows"] == 2

    relations = (
        await db.execute(
            select(StockRelation).where(StockRelation.source == "sector_match")
        )
    ).scalars().all()
    targets = {r.to_target for r in relations}
    assert targets == {"999421", "999422"}
    assert "999423" not in targets
    assert "999424" not in targets
