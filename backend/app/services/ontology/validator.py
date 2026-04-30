"""Universe-match + dedup for LLM-extracted relations.

Routes each `ExtractedRelation`:
  - both tickers in Tier 1+2 universe (active) → stock_relations bulk_upsert
  - exactly one side in universe (or neither) → relation_candidates buffer
  - same ticker on both sides → drop (LLM hallucination)

Confidence < `_REVIEW_FLOOR` is dropped entirely (would just pollute the graph).
Higher-confidence rows below `_REVIEW_THRESHOLD` are still persisted but flagged
for the future review queue (P1.9+ admin UI).

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §7 step 4
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import RelationCandidate, Stock
from app.services.ontology.schemas import ExtractedRelation
from app.services.ontology.upsert import bulk_upsert_relations

logger = logging.getLogger(__name__)

_TIER_USER_TOUCHED = 2
_REVIEW_FLOOR = 0.3  # below this → drop (too noisy to keep)
_REVIEW_THRESHOLD = 0.6  # below this → flagged in metadata for admin review

# Reciprocal type for the reverse direction. supply / contract are asymmetric
# (supplier ↔ customer); peer / competitor / complementary are symmetric.
_RECIPROCAL_TYPE: dict[str, str] = {
    "peer": "peer",
    "supply_upstream": "supply_downstream",
    "supply_downstream": "supply_upstream",
    "group": "group",
    "theme": "theme",
    "macro": "macro",
    "competitor": "competitor",
    "contract_supplier": "contract_customer",
    "contract_customer": "contract_supplier",
    "complementary": "complementary",
    "regulatory_link": "regulatory_link",
}


async def validate_and_route(
    relations: list[ExtractedRelation],
    *,
    source: str,
    session: AsyncSession | None = None,
) -> dict:
    """Persist extracted relations to either `stock_relations` (both sides in
    universe) or `relation_candidates` (Tier 3 buffer).

    `source` distinguishes provenance (e.g. "dart_contract", "sec_8k", "news").
    Pass `session` to reuse caller transaction (test fixtures); otherwise opens
    own session and commits.
    """
    if not relations:
        return {"received": 0, "upserted": 0, "buffered": 0, "dropped": 0}

    if session is not None:
        return await _route(session, relations, source)
    async with async_session() as own:
        summary = await _route(own, relations, source)
        await own.commit()
        return summary


async def _route(
    session: AsyncSession, relations: list[ExtractedRelation], source: str
) -> dict:
    deduped, dropped_self = _dedupe_inputs(relations)

    universe_tickers: set[str] = set()
    for rel in deduped:
        universe_tickers.add(rel.from_ticker)
        universe_tickers.add(rel.to_ticker)

    universe_rows = (
        await session.execute(
            select(Stock.id, Stock.ticker).where(
                Stock.ticker.in_(universe_tickers),
                Stock.tier <= _TIER_USER_TOUCHED,
                Stock.is_delisted.is_(False),
            )
        )
    ).all()
    universe_ids: dict[str, int] = {r.ticker: r.id for r in universe_rows}

    upsert_payload: list[dict] = []
    candidate_payload: list[dict] = []
    dropped_low_conf = 0

    for rel in deduped:
        if rel.confidence < _REVIEW_FLOOR:
            dropped_low_conf += 1
            continue

        from_id = universe_ids.get(rel.from_ticker)
        to_in_universe = rel.to_ticker in universe_ids

        metadata = dict(rel.extra_metadata)
        if rel.rationale and "rationale" not in metadata:
            metadata["rationale"] = rel.rationale
        if rel.confidence < _REVIEW_THRESHOLD:
            metadata["needs_review"] = True

        if from_id is not None and to_in_universe:
            upsert_payload.append(_relation_row(rel, from_id, source, metadata))
            # Reciprocal — so the *other* card surfaces this edge too. Type
            # swaps for asymmetric relations (supplier ↔ customer); identity
            # for symmetric ones (peer / competitor / complementary / ...).
            reverse_type = _RECIPROCAL_TYPE.get(rel.relation_type, rel.relation_type)
            to_id = universe_ids[rel.to_ticker]
            upsert_payload.append({
                "from_stock_id": to_id,
                "to_target": rel.from_ticker,
                "to_kind": "stock",
                "relation_type": reverse_type,
                "strength": rel.strength,
                "source": source,
                "signal_direction": rel.signal_direction,
                "confidence": rel.confidence,
                "valid_from": rel.valid_from,
                "valid_until": rel.valid_until,
                "metadata": metadata or None,
            })
        else:
            candidate_payload.append(_candidate_row(rel, source, metadata))

    upserted = await bulk_upsert_relations(upsert_payload, session=session) if upsert_payload else 0
    buffered = await _bulk_insert_candidates(session, candidate_payload) if candidate_payload else 0

    summary = {
        "received": len(relations),
        "deduped": len(deduped),
        "self_loop_dropped": dropped_self,
        "low_conf_dropped": dropped_low_conf,
        "upserted": upserted,
        "buffered": buffered,
    }
    logger.info("ontology validate_and_route(%s): %s", source, summary)
    return summary


def _dedupe_inputs(relations: list[ExtractedRelation]) -> tuple[list[ExtractedRelation], int]:
    """Drop self-loops and (from, to, type) duplicates within one batch.
    On collision keep the higher-confidence row.
    """
    self_loops = 0
    by_key: dict[tuple[str, str, str], ExtractedRelation] = {}
    for rel in relations:
        if rel.from_ticker == rel.to_ticker:
            self_loops += 1
            continue
        key = (rel.from_ticker, rel.to_ticker, rel.relation_type)
        existing = by_key.get(key)
        if existing is None or rel.confidence > existing.confidence:
            by_key[key] = rel
    return list(by_key.values()), self_loops


def _relation_row(
    rel: ExtractedRelation, from_id: int, source: str, metadata: dict
) -> dict:
    return {
        "from_stock_id": from_id,
        "to_target": rel.to_ticker,
        "to_kind": "stock",
        "relation_type": rel.relation_type,
        "strength": rel.strength,
        "source": source,
        "signal_direction": rel.signal_direction,
        "confidence": rel.confidence,
        "valid_from": rel.valid_from,
        "valid_until": rel.valid_until,
        "metadata": metadata or None,
    }


def _candidate_row(rel: ExtractedRelation, source: str, metadata: dict) -> dict:
    return {
        "from_ticker": rel.from_ticker,
        "to_ticker": rel.to_ticker,
        "relation_type": rel.relation_type,
        "signal_direction": rel.signal_direction,
        "strength": rel.strength,
        "confidence": rel.confidence,
        "source": source,
        "source_url": metadata.get("source_url"),
        "metadata": metadata or None,
    }


async def _bulk_insert_candidates(
    session: AsyncSession, payload: list[dict]
) -> int:
    """Insert into relation_candidates. No ON CONFLICT — duplicates are tolerated;
    promotion path dedupes by (from_ticker, to_ticker, relation_type) at scan time.
    Bypasses ORM by inserting against the Table directly to avoid SQLAlchemy's
    `metadata` reserved-attribute conflict."""
    table = RelationCandidate.__table__
    stmt = pg_insert(table).values(payload)
    await session.execute(stmt)
    return len(payload)
