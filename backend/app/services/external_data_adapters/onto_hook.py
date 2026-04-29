"""Onto layer auto-population — runs after a Stock row is inserted.

Spec §9. Enriches the freshly registered Stock via its primary adapter:
- SectorInfo → `Stock.sector` update
- Same-sector existing stocks → `stock_relations` rows
  (`relation_type=peer`, `source=auto_sector_match`, strength=0.5)
- KR only: dartlab industry graph fetch (schema-level probe; full
  supply_upstream/downstream extraction is P1.6's relation pipeline)

Everything is best-effort — failures log and degrade. A flaky external
API must never block stock registration. Concurrent writers (this hook
plus the bg `llm_discover_relations` refresh) are safe via the
`(from, to, type, source)` UNIQUE + on_conflict_do_update introduced
in alembic `a68d8f268caf`.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock
from app.models.relation import StockRelation
from app.services.external_data_adapters import (
    DartlabAdapter,
    SectorInfo,
    get_adapter_for,
)

logger = logging.getLogger(__name__)

AUTO_SOURCE_SECTOR = "auto_sector_match"
DEFAULT_PEER_STRENGTH = 0.5


async def enrich_stock_after_register(
    stock_id: int, ticker: str, db: AsyncSession
) -> dict:
    """Run sector + onto auto-population after a Stock row is inserted.

    Returns a small report dict — production callers fire-and-forget and
    don't block on this; the report is for tests / observability.
    """
    report = {"sector_set": False, "peers_added": 0, "industry_probed": False}

    sector = await _safe_fetch_sector(ticker)
    if sector is None or sector.sector == "Unknown":
        # No usable sector → nothing to anchor peers on.
        await db.commit()
        return report

    await _update_stock_sector(stock_id, sector, db)
    report["sector_set"] = True

    peers_added = await _register_sector_peers(stock_id, sector, db)
    report["peers_added"] = peers_added

    # KR-only industry probe. Schema-level only — P1.6 will turn the resulting
    # IndustryGraph into supply_upstream/downstream rows. Today we just verify
    # the call path so the contract sticks before the extraction work lands.
    industry_probed = await _probe_industry(ticker, sector)
    report["industry_probed"] = industry_probed

    await db.commit()
    return report


async def _safe_fetch_sector(ticker: str) -> Optional[SectorInfo]:
    try:
        adapter = get_adapter_for(ticker)
        return await adapter.fetch_sector(ticker)
    except Exception as e:  # noqa: BLE001 — degrade quietly
        logger.warning("enrich_stock fetch_sector failed for %s: %s", ticker, e)
        return None


async def _update_stock_sector(
    stock_id: int, sector: SectorInfo, db: AsyncSession
) -> None:
    stock = await db.get(Stock, stock_id)
    if stock is None:
        return
    stock.sector = sector.sector


async def _register_sector_peers(
    stock_id: int, sector: SectorInfo, db: AsyncSession
) -> int:
    """Same-sector stocks → peer rows. Idempotent via on_conflict_do_update."""
    result = await db.execute(
        select(Stock).where(
            Stock.sector == sector.sector,
            Stock.id != stock_id,
        )
    )
    peers = result.scalars().all()
    if not peers:
        return 0

    rows = [
        {
            "from_stock_id": stock_id,
            "to_target": p.ticker,
            "to_kind": "stock",
            "relation_type": "peer",
            "strength": DEFAULT_PEER_STRENGTH,
            "source": AUTO_SOURCE_SECTOR,
        }
        for p in peers
    ]
    stmt = pg_insert(StockRelation).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_relation_triple",
        set_={
            "strength": stmt.excluded.strength,
            "refreshed_at": stmt.excluded.refreshed_at,
        },
    )
    await db.execute(stmt)
    return len(peers)


async def _probe_industry(ticker: str, sector: SectorInfo) -> bool:
    """KR-only industry-graph probe. Returns True if the fetch ran (regardless
    of result), False if skipped (US ticker / no industry_group)."""
    industry_id = sector.industry_group or sector.sector
    if not industry_id:
        return False
    try:
        adapter = get_adapter_for(ticker)
    except Exception:  # noqa: BLE001 — bad ticker shouldn't kill enrichment
        return False
    if not isinstance(adapter, DartlabAdapter):
        return False
    try:
        await adapter.fetch_industry_graph(industry_id)
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("industry probe for %s skipped: %s", ticker, e)
        return False
