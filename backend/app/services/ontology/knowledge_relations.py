"""LLM 사전 지식 기반 핵심 사업 관계 추출 — passive extraction 한계 보완.

기존 추출 (extract_news / extract_sec / sector_match) 는 본문 인용 또는
GICS bucket 기반 — 본문에 명시되지 않은 관계 + 비상장 entity (OpenAI,
SpaceX, ByteDance) 는 못 잡음.

이 모듈은 active — 시니어 펀더멘털 분석가 페르소나 LLM 이 자기 사전 지식
으로 "이 회사 매수 결정에 진짜 영향을 줄 핵심 관계 5-10 개" 직접 답한다.

가드 (동화약품 같은 환상 재발 방지 4 layer):
  1. relation_kind 7종 whitelist (한국어 입력 → 영문 type 매핑)
  2. business_importance ≥ 3 (5 등급 중 매수 결정 영향 있는 것만)
  3. reasoning ≥ 80 chars + 구체성 (단순 "협력 관계" 거부)
  4. confidence ≥ 0.7; knowledge_cutoff_risk="high" 면 cap 0.6 → 자동 drop

저장:
  - target 상장 + universe 안: `StockRelation` (source="llm_knowledge")
  - 비상장 OR universe 밖: `RelationCandidate` (source="llm_knowledge",
    to_ticker 자리에 회사명 또는 가공 식별자). 사용자에게 "전략 파트너 (비상장)"
    섹션으로 surface 예정.

비용: gpt-5 1 회 ~$0.01-0.02. analyze() 시점 1 회 호출.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import RelationCandidate, Stock, StockRelation

logger = logging.getLogger(__name__)

KNOWLEDGE_SOURCE = "llm_knowledge"

_MIN_CONFIDENCE = 0.7
_MIN_IMPORTANCE = 3
_MIN_REASONING_CHARS = 80
_CUTOFF_HIGH_CONFIDENCE_CAP = 0.6  # → automatically drops (< _MIN_CONFIDENCE)

# 한국어 분석가 출력 → DB relation_type 매핑. 기존 11종 안에서 해결.
# 새 type 추가하면 스키마 / pydantic literal / migration / frontend 다 손대야
# 함 — 일단 기존 type 재사용으로 ship 후 필요시 확장.
_RELATION_TYPE_MAP: dict[str, str] = {
    "핵심파트너": "complementary",       # mutual value (예: MS↔OpenAI)
    "핵심공급사": "contract_supplier",   # focal is downstream (예: MS↔NVDA)
    "핵심고객": "contract_customer",     # focal is upstream
    "핵심경쟁사": "competitor",          # direct rival
    "투자_지분": "group",                # equity stake / corporate ownership
    "모회사": "group",
    "자회사": "group",
}

_PROMPT = (
    "당신은 30년 경력 펀더멘털 분석가다. 사용자의 매수/매도 결정에 진짜 영향을\n"
    "줄 핵심 사업 관계만 식별한다. 추측은 자본 손실로 이어진다.\n\n"
    "분석 대상: {ticker} ({name}, market={market}, sector={sector}).\n\n"
    "각 관계마다 JSON object:\n"
    "- target_name: 회사명 (한국어 또는 영문 정식명)\n"
    "- target_ticker: 상장사면 ticker (모르면 빈 문자열)\n"
    "- target_is_public: true | false\n"
    '- relation_kind: "핵심파트너" | "핵심공급사" | "핵심고객" | "핵심경쟁사" |\n'
    '                 "투자_지분" | "모회사" | "자회사"\n'
    "- business_importance: 1 (주변) ~ 5 (매수 결정 핵심)\n"
    "- reasoning: 2-3 문장, 구체적 (매출/이익 의존도 %, 대체 가능성, 계약 규모).\n"
    '            "협력 관계" / "사업 연관" 같은 막연 표현 금지.\n'
    '- knowledge_cutoff_risk: "high" (training 이후 변경 가능) | "low"\n'
    "- confidence: 0.0~1.0\n\n"
    "엄격 규칙:\n"
    "1. 확실하지 않으면 빈 list. 추측 금지.\n"
    "2. business_importance < 3 은 출력 X.\n"
    "3. relation_kind 7종 외 금지.\n"
    "4. reasoning < 80자면 출력 X.\n"
    "5. 비상장 entity (OpenAI, SpaceX, ByteDance 등) 도 포함 — 단 진짜 알 때만.\n"
    '6. knowledge_cutoff_risk="high" 이면 confidence ≤ 0.6 (자동 drop 됨).\n\n'
    '응답 형식: {{"relations": [...]}}. JSON 1개. 자연어 / 코드펜스 X.'
)


async def extract_knowledge_relations(ticker: str) -> dict:
    """Senior analyst persona LLM 으로 핵심 관계 추출 + 저장.

    예외 swallow — 비용/네트워크 문제로 analyze() 전체 흐름 깨지지 X.
    """
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"error": f"stock {ticker} not found"}

    prompt = _PROMPT.format(
        ticker=stock.ticker,
        name=stock.name or stock.ticker,
        market=stock.market or "?",
        sector=stock.sector or "?",
    )

    try:
        from app.services.llm.adapter import get_adapter

        raw = await get_adapter().generate_json(prompt)
    except Exception as e:  # noqa: BLE001
        logger.warning("knowledge_relations LLM failed for %s: %s", ticker, e)
        return {"error": str(e)}

    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as e:
        logger.warning("knowledge_relations JSON parse failed for %s: %s", ticker, e)
        return {"error": "parse_failed"}

    if not isinstance(parsed, dict):
        return {"error": "non_dict_response"}
    raw_rels = parsed.get("relations") or []
    if not isinstance(raw_rels, list):
        return {"error": "relations_not_list"}

    return await _validate_and_persist(stock, raw_rels)


async def _validate_and_persist(stock: Stock, raw_rels: list[dict]) -> dict:
    kept: list[dict] = []
    dropped_type = 0
    dropped_importance = 0
    dropped_reasoning = 0
    dropped_confidence = 0

    for r in raw_rels:
        if not isinstance(r, dict):
            continue

        # Layer 1 — relation_kind whitelist
        kind = (r.get("relation_kind") or "").strip()
        db_type = _RELATION_TYPE_MAP.get(kind)
        if db_type is None:
            dropped_type += 1
            continue

        # Layer 2 — business_importance ≥ 3
        try:
            importance = int(r.get("business_importance") or 0)
        except (TypeError, ValueError):
            dropped_importance += 1
            continue
        if importance < _MIN_IMPORTANCE:
            dropped_importance += 1
            continue
        importance = min(importance, 5)

        # Layer 3 — reasoning length + non-empty target
        reasoning = (r.get("reasoning") or "").strip()
        target_name = (r.get("target_name") or "").strip()
        if not target_name or len(reasoning) < _MIN_REASONING_CHARS:
            dropped_reasoning += 1
            continue

        # Layer 4 — confidence floor (knowledge_cutoff_risk=high cap first)
        try:
            conf = float(r.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        cutoff_risk = (r.get("knowledge_cutoff_risk") or "low").strip().lower()
        if cutoff_risk == "high" and conf > _CUTOFF_HIGH_CONFIDENCE_CAP:
            conf = _CUTOFF_HIGH_CONFIDENCE_CAP
        if conf < _MIN_CONFIDENCE:
            dropped_confidence += 1
            continue

        target_ticker = (r.get("target_ticker") or "").strip().upper()
        target_is_public = bool(r.get("target_is_public"))

        kept.append({
            "db_type": db_type,
            "relation_kind": kind,
            "importance": importance,
            "reasoning": reasoning,
            "confidence": conf,
            "cutoff_risk": cutoff_risk,
            "target_name": target_name,
            "target_ticker": target_ticker,
            "target_is_public": target_is_public,
        })

    if not kept:
        return _summary(len(raw_rels), 0, 0, dropped_type, dropped_importance,
                        dropped_reasoning, dropped_confidence)

    upserted_stock, upserted_cand = await _persist(stock, kept)
    return _summary(
        len(raw_rels), upserted_stock, upserted_cand,
        dropped_type, dropped_importance, dropped_reasoning, dropped_confidence,
    )


async def _persist(stock: Stock, kept: list[dict]) -> tuple[int, int]:
    """target 가 universe 안의 상장 ticker 면 StockRelation, 그 외엔
    RelationCandidate. 비상장 (OpenAI 등) 도 candidate 경유로 저장."""
    upserted_stock = 0
    upserted_cand = 0
    async with async_session() as db:
        for r in kept:
            target_stock = None
            if r["target_ticker"] and r["target_is_public"]:
                target_stock = (
                    await db.execute(
                        select(Stock).where(Stock.ticker == r["target_ticker"])
                    )
                ).scalar_one_or_none()

            metadata = {
                "rationale": r["reasoning"],
                "business_importance": r["importance"],
                "knowledge_cutoff_risk": r["cutoff_risk"],
                "target_name": r["target_name"],
                "target_is_public": r["target_is_public"],
                "relation_kind_kr": r["relation_kind"],
            }
            # strength = 0.5 baseline + importance step (3→0.5, 5→0.7).
            strength = min(0.5 + 0.1 * (r["importance"] - 3), 1.0)

            if target_stock and target_stock.id != stock.id:
                table = StockRelation.__table__
                stmt = (
                    pg_insert(table)
                    .values(
                        from_stock_id=stock.id,
                        to_target=target_stock.ticker,
                        to_kind="stock",
                        relation_type=r["db_type"],
                        signal_direction="positive",
                        strength=strength,
                        confidence=r["confidence"],
                        source=KNOWLEDGE_SOURCE,
                        metadata=metadata,
                        is_active=True,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            "from_stock_id", "to_target", "relation_type", "source",
                        ],
                        set_={
                            "strength": strength,
                            "confidence": r["confidence"],
                            "metadata": metadata,
                            "is_active": True,
                            "refreshed_at": func.now(),
                        },
                    )
                )
                await db.execute(stmt)
                upserted_stock += 1
            else:
                # 비상장 OR universe 밖 — candidate 로 buffer. to_ticker 자리에
                # ticker 가 없으면 회사명 약식 (20 chars 한도).
                slot = r["target_ticker"] or r["target_name"][:20]
                table = RelationCandidate.__table__
                stmt = (
                    pg_insert(table)
                    .values(
                        from_ticker=stock.ticker,
                        to_ticker=slot,
                        relation_type=r["db_type"],
                        signal_direction="positive",
                        strength=strength,
                        confidence=r["confidence"],
                        source=KNOWLEDGE_SOURCE,
                        metadata=metadata,
                    )
                )
                await db.execute(stmt)
                upserted_cand += 1
        await db.commit()
    return upserted_stock, upserted_cand


def _summary(
    received: int, upserted_stock: int, upserted_cand: int,
    dropped_type: int, dropped_importance: int,
    dropped_reasoning: int, dropped_confidence: int,
) -> dict:
    return {
        "received": received,
        "upserted_stock_relations": upserted_stock,
        "upserted_candidates": upserted_cand,
        "dropped_type": dropped_type,
        "dropped_importance": dropped_importance,
        "dropped_reasoning": dropped_reasoning,
        "dropped_confidence": dropped_confidence,
    }
