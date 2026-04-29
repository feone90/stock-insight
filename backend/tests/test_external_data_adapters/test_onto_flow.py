"""onto_hook — spec §9 5 unit cases (uses transactional `db` fixture)."""
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import Stock
from app.models.relation import StockRelation
from app.services.external_data_adapters.base import IndustryGraph, SectorInfo
from app.services.external_data_adapters.cache import ResultCache
from app.services.external_data_adapters.dartlab_adapter import DartlabAdapter
from app.services.external_data_adapters.onto_hook import (
    enrich_stock_after_register,
)
from app.services.external_data_adapters.sec_edgar_adapter import SecEdgarAdapter


def _kr_sector(name: str = "IT") -> SectorInfo:
    return SectorInfo(
        sector=name,
        industry_group="Semiconductors",
        confidence=1.0,
        source="dartlab",
    )


def _us_sector(name: str = "Information Technology") -> SectorInfo:
    return SectorInfo(
        sector=name,
        industry_group=None,
        confidence=0.7,
        source="sec_edgar_sic",
    )


def _make_kr_adapter(sector: SectorInfo) -> DartlabAdapter:
    """Real DartlabAdapter instance with fetch_* methods stubbed.
    Real type is required because onto_hook checks `isinstance(..., DartlabAdapter)`.
    """
    adapter = DartlabAdapter(cache=ResultCache())
    adapter.fetch_sector = AsyncMock(return_value=sector)
    adapter.fetch_industry_graph = AsyncMock(
        return_value=IndustryGraph(
            industry_id="semiconductors", nodes=[], edges=[], source="dartlab"
        )
    )
    return adapter


def _make_us_adapter(sector: SectorInfo) -> SecEdgarAdapter:
    adapter = SecEdgarAdapter(cache=ResultCache())
    adapter.fetch_sector = AsyncMock(return_value=sector)
    return adapter


@pytest_asyncio.fixture
async def kr_existing_peer(db):
    peer = Stock(ticker="000660", name="SK하이닉스", market="KR", sector="IT")
    db.add(peer)
    await db.flush()
    return peer


@pytest_asyncio.fixture
async def us_existing_peer(db):
    peer = Stock(
        ticker="MSFT",
        name="Microsoft",
        market="US",
        sector="Information Technology",
    )
    db.add(peer)
    await db.flush()
    return peer


@pytest.mark.asyncio
async def test_kr_new_stock_registers_peer_with_same_sector(
    monkeypatch, db, kr_existing_peer
):
    new_stock = Stock(ticker="999999", name="테스트반도체", market="KR", sector="")
    db.add(new_stock)
    await db.flush()

    adapter = _make_kr_adapter(_kr_sector("IT"))
    monkeypatch.setattr(
        "app.services.external_data_adapters.onto_hook.get_adapter_for",
        lambda _t: adapter,
    )

    report = await enrich_stock_after_register(new_stock.id, new_stock.ticker, db)

    assert report["sector_set"] is True
    assert report["peers_added"] == 1

    rels = (
        await db.execute(
            select(StockRelation).where(StockRelation.from_stock_id == new_stock.id)
        )
    ).scalars().all()
    assert len(rels) == 1
    assert rels[0].to_target == "000660"
    assert rels[0].relation_type == "peer"
    assert rels[0].source == "auto_sector_match"


@pytest.mark.asyncio
async def test_us_new_stock_registers_peer_via_sec_edgar(
    monkeypatch, db, us_existing_peer
):
    new_stock = Stock(ticker="AAPL", name="Apple Inc.", market="US", sector="")
    db.add(new_stock)
    await db.flush()

    adapter = _make_us_adapter(_us_sector("Information Technology"))
    monkeypatch.setattr(
        "app.services.external_data_adapters.onto_hook.get_adapter_for",
        lambda _t: adapter,
    )

    report = await enrich_stock_after_register(new_stock.id, new_stock.ticker, db)

    assert report["sector_set"] is True
    assert report["peers_added"] == 1
    assert report["industry_probed"] is False  # US has no DartlabAdapter

    rels = (
        await db.execute(
            select(StockRelation).where(StockRelation.from_stock_id == new_stock.id)
        )
    ).scalars().all()
    assert len(rels) == 1
    assert rels[0].to_target == "MSFT"
    assert rels[0].source == "auto_sector_match"


@pytest.mark.asyncio
async def test_unknown_sector_registers_no_peers(monkeypatch, db, us_existing_peer):
    """Sector='Unknown' (SIC mapping miss) anchors no peer relation."""
    new_stock = Stock(ticker="WEIRD", name="Weird Co", market="US", sector="")
    db.add(new_stock)
    await db.flush()

    unknown = SectorInfo(
        sector="Unknown",
        industry_group=None,
        confidence=0.3,
        source="sec_edgar_sic",
    )
    adapter = _make_us_adapter(unknown)
    monkeypatch.setattr(
        "app.services.external_data_adapters.onto_hook.get_adapter_for",
        lambda _t: adapter,
    )

    report = await enrich_stock_after_register(new_stock.id, new_stock.ticker, db)

    assert report["sector_set"] is False
    assert report["peers_added"] == 0


@pytest.mark.asyncio
async def test_kr_industry_probe_invokes_dartlab_industry_graph(
    monkeypatch, db, kr_existing_peer
):
    """KR ticker → industry probe runs (Phase A delivers schema-level only)."""
    new_stock = Stock(ticker="999999", name="테스트반도체", market="KR", sector="")
    db.add(new_stock)
    await db.flush()

    adapter = _make_kr_adapter(_kr_sector("IT"))
    monkeypatch.setattr(
        "app.services.external_data_adapters.onto_hook.get_adapter_for",
        lambda _t: adapter,
    )

    report = await enrich_stock_after_register(new_stock.id, new_stock.ticker, db)

    assert report["industry_probed"] is True
    adapter.fetch_industry_graph.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_writer_idempotent_no_duplicate_rows(
    monkeypatch, db, kr_existing_peer
):
    """Calling the hook twice (post-save + bg refresh race) keeps row count
    stable thanks to (from, to, type, source) UNIQUE + on_conflict_do_update."""
    new_stock = Stock(ticker="999999", name="테스트반도체", market="KR", sector="")
    db.add(new_stock)
    await db.flush()

    adapter = _make_kr_adapter(_kr_sector("IT"))
    monkeypatch.setattr(
        "app.services.external_data_adapters.onto_hook.get_adapter_for",
        lambda _t: adapter,
    )

    await enrich_stock_after_register(new_stock.id, new_stock.ticker, db)
    await enrich_stock_after_register(new_stock.id, new_stock.ticker, db)

    rels = (
        await db.execute(
            select(StockRelation).where(StockRelation.from_stock_id == new_stock.id)
        )
    ).scalars().all()
    assert len(rels) == 1
