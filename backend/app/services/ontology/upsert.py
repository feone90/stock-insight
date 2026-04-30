"""Bulk upsert + Tier 3 candidate promotion.

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §5.3, §7
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §4
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import RelationCandidate, Stock, StockRelation

logger = logging.getLogger(__name__)

_BATCH_SIZE = 1000
_TIER_USER_TOUCHED = 2


async def bulk_upsert_relations(
    rows: list[dict], *, session: AsyncSession | None = None
) -> int:
    """Upsert StockRelation rows in 1000-row chunks.

    Pass `session` to reuse a caller-managed transaction (test fixtures);
    otherwise an own `async_session()` is opened and committed at the end.

    On conflict (from_stock_id, to_target, relation_type, source):
      - strength → average of old & new (smooth re-discovery noise)
      - confidence → MAX (best evidence wins)
      - refreshed_at → NOW()
    """
    if not rows:
        return 0
    if session is not None:
        return await _upsert_all(session, rows)

    total = 0
    async with async_session() as own:
        total = await _upsert_all(own, rows)
        await own.commit()
    return total


async def _upsert_all(session: AsyncSession, rows: list[dict]) -> int:
    total = 0
    for chunk in _chunked(rows, _BATCH_SIZE):
        total += await _upsert_chunk(session, chunk)
    return total


async def _upsert_chunk(session: AsyncSession, chunk: list[dict]) -> int:
    """Insert against the Table directly to bypass ORM `metadata` reserved-name
    conflict (rows carrying a `metadata` key crash SQLAlchemy bulk update path)."""
    table = StockRelation.__table__
    stmt = pg_insert(table).values(chunk)
    stmt = stmt.on_conflict_do_update(
        index_elements=["from_stock_id", "to_target", "relation_type", "source"],
        set_={
            "strength": (table.c.strength + stmt.excluded.strength) / 2,
            "confidence": func.greatest(table.c.confidence, stmt.excluded.confidence),
            "signal_direction": stmt.excluded.signal_direction,
            "refreshed_at": func.now(),
        },
    )
    await session.execute(stmt)
    return len(chunk)


async def scan_pending_candidates(
    stock_id: int, *, session: AsyncSession | None = None
) -> int:
    """P1.7 hook — Tier 3→1/2 승격 시 호출.

    `relation_candidates`에서 양쪽 ticker가 모두 Tier 1+2 universe에 있는 pending
    row를 찾아 `stock_relations`로 promote + `promoted_at` 마킹.

    fire-and-forget 안전 — 예외는 swallow + log.
    Pass `session` to reuse caller transaction (test fixtures).
    """
    try:
        if session is not None:
            return await _scan_with_session(session, stock_id)
        async with async_session() as own:
            promoted = await _scan_with_session(own, stock_id)
            await own.commit()
            return promoted
    except Exception as e:  # noqa: BLE001 — fire-and-forget; never crash caller
        logger.warning("scan_pending_candidates(stock_id=%s) failed: %s", stock_id, e)
        return 0


async def _scan_with_session(session: AsyncSession, stock_id: int) -> int:
    ticker = (
        await session.execute(select(Stock.ticker).where(Stock.id == stock_id))
    ).scalar_one_or_none()
    if ticker is None:
        return 0
    return await _promote_candidates_for(session, ticker)


async def _promote_candidates_for(session: AsyncSession, ticker: str) -> int:
    """Pull pending candidates touching `ticker` whose other side is also in
    Tier 1+2 universe; insert StockRelation rows and mark promoted_at.
    """
    pending = (
        await session.execute(
            select(RelationCandidate).where(
                RelationCandidate.promoted_at.is_(None),
                (RelationCandidate.from_ticker == ticker)
                | (RelationCandidate.to_ticker == ticker),
            )
        )
    ).scalars().all()
    if not pending:
        return 0

    other_tickers = {
        c.to_ticker if c.from_ticker == ticker else c.from_ticker for c in pending
    }
    other_tickers.add(ticker)
    universe_rows = (
        await session.execute(
            select(Stock.id, Stock.ticker).where(
                Stock.ticker.in_(other_tickers),
                Stock.tier <= _TIER_USER_TOUCHED,
                Stock.is_delisted.is_(False),
            )
        )
    ).all()
    universe_ids = {r.ticker: r.id for r in universe_rows}

    promoted = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for cand in pending:
        from_id = universe_ids.get(cand.from_ticker)
        if from_id is None or cand.to_ticker not in universe_ids:
            continue  # other side still outside universe — keep buffered
        relation_row = await _insert_relation_from_candidate(session, cand, from_id)
        # Raw UPDATE bypasses ORM's `metadata`-attribute conflict (RelationCandidate
        # exposes the JSONB column under a different Python name; ORM dirty
        # tracking still resolves "metadata" against SQLAlchemy's reserved
        # MetaData attribute and crashes the flush).
        await session.execute(
            update(RelationCandidate)
            .where(RelationCandidate.id == cand.id)
            .values(promoted_at=now, promoted_to_relation_id=relation_row.id)
        )
        promoted += 1
    return promoted


async def _insert_relation_from_candidate(
    session: AsyncSession, cand: RelationCandidate, from_id: int
) -> StockRelation:
    """Single-row upsert for the promote path. ON CONFLICT preserves prior
    metadata (rare collision — same edge already imported via another source).

    Bypasses ORM `metadata` reserved-name conflict by inserting against the
    Table directly, then re-fetches via ORM for the returned id.
    """
    table = StockRelation.__table__
    payload = {
        "from_stock_id": from_id,
        "to_target": cand.to_ticker,
        "to_kind": "stock",
        "relation_type": cand.relation_type,
        "strength": cand.strength if cand.strength is not None else 0.5,
        "source": cand.source or "candidate_promote",
        "signal_direction": cand.signal_direction,
        "confidence": cand.confidence if cand.confidence is not None else 0.5,
        "metadata": cand.extra_metadata,
    }
    stmt = pg_insert(table).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["from_stock_id", "to_target", "relation_type", "source"],
        set_={
            "refreshed_at": func.now(),
            "is_active": True,
        },
    ).returning(table.c.id)
    result = await session.execute(stmt)
    relation_id = result.scalar_one()
    return (
        await session.execute(select(StockRelation).where(StockRelation.id == relation_id))
    ).scalar_one()


def _chunked(rows: Iterable[dict], size: int) -> Iterator[list[dict]]:
    buf: list[dict] = []
    for r in rows:
        buf.append(r)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


__all__ = [
    "bulk_upsert_relations",
    "scan_pending_candidates",
]
