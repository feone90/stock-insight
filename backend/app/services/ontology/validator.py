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
_REVIEW_FLOOR = 0.5  # below this → drop. 시황 기사에서 LLM 이 만든 약신호 차단.
_REVIEW_THRESHOLD = 0.75  # below this → 정성적 추정. metadata.needs_review=True 로 flag.

# 2026-05-14 LLM hallucination 가드. 사용자가 SK하이닉스 카드에서 동화약품
# (의약품 종목) complementary 0.86 으로 잡힌 것 발견. 본문에 "동화약품" 0회
# 등장 — 100% LLM 환상. extract_news 의 substring gate 가 있지만 옛 추출
# 잔재 + paraphrase 자체 검증 부족.
#
# 새 룰: LLM 기반 source 는 rationale (텍스트 인용) 반드시 필요. 없거나
# 너무 짧으면 (의미 있는 인용은 30+ char) drop. sector_match 같은 mechanical
# rule source 는 rationale 없는 게 정상.
_LLM_SOURCES_REQUIRING_RATIONALE = frozenset({
    "news", "sec_8k", "sec_10k_risk", "dart_contract", "llm_web_search",
})
_MIN_RATIONALE_CHARS = 30

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
    dropped_no_rationale = 0
    dropped_no_target_name_evidence = 0
    dropped_self_negating = 0

    requires_rationale = source in _LLM_SOURCES_REQUIRING_RATIONALE

    for rel in deduped:
        if rel.confidence < _REVIEW_FLOOR:
            dropped_low_conf += 1
            continue

        # LLM hallucination 가드 — rationale 필수 source 인데 rationale 없거나
        # 너무 짧으면 drop. 본문 인용 없는 LLM 추출은 환상 가능성 ↑.
        if requires_rationale:
            rat = (rel.rationale or "").strip()
            meta_rat = ""
            if isinstance(rel.extra_metadata, dict):
                meta_rat = (rel.extra_metadata.get("rationale") or "").strip()
            longest = max(len(rat), len(meta_rat))
            if longest < _MIN_RATIONALE_CHARS:
                dropped_no_rationale += 1
                logger.info(
                    "validator drop hallucination candidate: src=%s %s→%s "
                    "type=%s conf=%.2f rationale_len=%d",
                    source, rel.from_ticker, rel.to_ticker, rel.relation_type,
                    rel.confidence, longest,
                )
                continue

            # 2026-05-15 — self-negating rationale (LLM 이 자기 입으로
            # "관계 없음" 자백). 실제 발견: NVDA↔McDonald's rationale 이
            # "NVDA와의 직접 관계는 없음". 100% 환상 — hard drop.
            from app.services.ontology.evidence import (
                rationale_admits_no_relationship,
            )
            combined_rationale = (rat + " " + meta_rat).strip()
            if rationale_admits_no_relationship(combined_rationale):
                dropped_self_negating += 1
                logger.info(
                    "validator drop self-negating: src=%s %s→%s rationale=%r",
                    source, rel.from_ticker, rel.to_ticker,
                    combined_rationale[:120],
                )
                continue

        # LLM hallucination 가드 (defense-in-depth) — rationale 안에 target
        # Stock.name 이 포함되어야 한다. extract_news 의 article-body substring
        # gate 와 동일 원칙을 validator 레이어에도 적용. paraphrase / 옛 row
        # 잔재 / extract_news 우회 경로 모두 차단.
        # 정규화: 한글 띄어쓰기 edge case ("SK 하이닉스" vs "SK하이닉스") 처리를
        # 위해 공백 전체 제거 후 비교.
        if requires_rationale:
            to_name_row = (
                await session.execute(
                    select(Stock.name).where(Stock.ticker == rel.to_ticker)
                )
            ).scalar_one_or_none()
            # Stock.name OR ticker 둘 중 하나가 rationale 에 등장해야 통과.
            # LLM 이 rationale 작성 시 회사명 대신 ticker 만 쓰는 경우 정상
            # ("EX0002 wins contract" 같은 abbreviated 표현). 둘 다 매칭 가능한데
            # 어느 쪽도 매칭 안 되면 환상.
            #
            # 1 자 (Ford="F", Visa="V") 는 매칭 신뢰성 zero — false positive
            # 거의 항상 통과. 후보 list 에서 제외. 둘 다 1 자면 가드 우회
            # (다른 가드: rationale 30+ chars, confidence floor 에 의존).
            to_name_norm = (
                "".join(to_name_row.split()).lower() if to_name_row else ""
            )
            to_ticker_norm = rel.to_ticker.lower()
            candidates = [
                c for c in (to_name_norm, to_ticker_norm) if len(c) >= 2
            ]
            if candidates:
                rat_combined = (rel.rationale or "") + " " + (
                    (rel.extra_metadata or {}).get("rationale") or ""
                )
                rat_norm = "".join(rat_combined.split()).lower()
                if not any(c in rat_norm for c in candidates):
                    dropped_no_target_name_evidence += 1
                    logger.info(
                        "validator drop no-target-evidence: src=%s %s→%s "
                        "type=%s conf=%.2f target_name=%r ticker=%s",
                        source, rel.from_ticker, rel.to_ticker,
                        rel.relation_type, rel.confidence, to_name_row,
                        rel.to_ticker,
                    )
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

    # Same batch can hit the same (from, to, type, source) twice when multiple
    # articles extract the same edge or when forward+reciprocal collapse.
    # Postgres ON CONFLICT can only act on one tuple per command, so collapse.
    upsert_payload = _dedupe_payload(upsert_payload)
    upserted = await bulk_upsert_relations(upsert_payload, session=session) if upsert_payload else 0
    buffered = await _bulk_insert_candidates(session, candidate_payload) if candidate_payload else 0

    summary = {
        "received": len(relations),
        "deduped": len(deduped),
        "self_loop_dropped": dropped_self,
        "low_conf_dropped": dropped_low_conf,
        "no_rationale_dropped": dropped_no_rationale,
        "no_target_name_evidence_dropped": dropped_no_target_name_evidence,
        "self_negating_dropped": dropped_self_negating,
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


def _dedupe_payload(payload: list[dict]) -> list[dict]:
    """Collapse duplicate (from_stock_id, to_target, relation_type, source) rows.
    Last write wins — later articles / reciprocal pass typically carry the
    higher-confidence version."""
    by_key: dict[tuple, dict] = {}
    for row in payload:
        key = (
            row.get("from_stock_id"),
            row.get("to_target"),
            row.get("relation_type"),
            row.get("source"),
        )
        existing = by_key.get(key)
        if existing is None or (row.get("confidence") or 0) >= (existing.get("confidence") or 0):
            by_key[key] = row
    return list(by_key.values())


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
