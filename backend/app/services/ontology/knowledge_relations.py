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

_PROMPT = """역할: 너는 30년 경력 펀더멘털 분석가다. 사용자의 매수/매도 결정에 *진짜 영향을 줄* 핵심 사업 관계만 식별한다. 추측은 자본 손실로 이어진다.

가장 중요한 원칙 (source document 없는 추출 — 더 엄격해야 함):
- 본 추출은 *너의 사전 지식* 으로만 한다. 본문 인용 없음.
- 따라서 모든 출력은 *공개 사실로 검증 가능*해야 함. 추측·소문·기대·계열 가능성 X.
- 매출/이익 비중, 계약 규모, 지분 % 같은 정량 근거 *없이* "협력 관계" 만 적으면 무가치 — drop 대상.
- LLM training cutoff 이후 큰 변동 가능 (인수/매각/파트너십 종료) — 확신 안 서면 knowledge_cutoff_risk="high".

비상장 핵심 파트너 식별 의무 (사용자 정직한 요청):
- 사용자가 가장 가치 있다고 느끼는 관계는 *상장사 간* 이 아니라 *비상장 핵심 파트너* 다.
  상장사 관계는 sector_match / news / SEC 가 이미 잡지만, 비상장은 이 모듈만의 책임.
- Hyperscaler / mega-cap tech 분석 시 다음 비상장 entity 들 *반드시* 검토:
  * AI 파트너십: OpenAI (MS 49% 지분 + Azure exclusive), Anthropic (AMZN 80억 투자 + AWS),
    xAI (TSLA/X 동일 오너), DeepMind (GOOG 인수 자회사)
  * 클라우드 / 데이터: Databricks, Snowflake (이미 상장 — IT)
  * 우주/로봇: SpaceX (TSLA 동일 오너), Boston Dynamics (HYUNDAI 인수)
- 진짜 알 때만 — 일반적으로 알려진 사실만. 안 확실하면 빠뜨려도 됨, 추측은 절대 금지.
- target_ticker 는 빈 문자열, target_is_public=false 로 박을 것 — RelationCandidate 로
  자동 routing.

분석 대상: {ticker} ({name}, market={market}, sector={sector})

먼저 수행할 BUSINESS DOMAIN IDENTIFICATION:
Step 1: 이 회사의 핵심 사업 영역 2-4개 (예: MS = Cloud Azure / AI / 게이밍 / 운영체제·Office).
Step 2: 각 사업 영역마다 매수 결정에 *영향* 줄 회사 관계 식별:
  - 핵심 공급사 (없으면 사업 멈춤)
  - 핵심 고객 (없으면 매출 직격)
  - 핵심 경쟁사 (점유율 직접 경쟁)
  - 핵심 파트너 (생태계 의존)
  - 모/자회사 / 투자 지분 (법적·재무 연결)
Step 3: 정량 근거 가능한 관계만 keep. 막연한 "관련 업체" / "협력 가능성" drop.

각 관계 JSON object:
- target_name: 회사명 (한국어 또는 영문 정식명)
- target_ticker: 상장사면 ticker (모르면 빈 문자열)
- target_is_public: true | false
- relation_kind: "핵심파트너" | "핵심공급사" | "핵심고객" | "핵심경쟁사" | "투자_지분" | "모회사" | "자회사"
- business_importance: 1 (주변 관계) ~ 5 (매수 결정 핵심)
- reasoning: 2-3 문장. *반드시* 정량 근거 포함:
  * 매출/이익 의존도 % 또는
  * 계약 규모 (KRW / USD) 또는
  * 지분 % 또는
  * 시장 점유율 % 또는
  * 단일 공급/sole source 명시
  "협력 관계", "전략적 파트너", "사업 연관" 같은 막연 표현 금지 — drop.
- knowledge_cutoff_risk: "high" | "low"
- confidence: 0.0~1.0

HEDGE / VAGUE 즉시 거절:
다음 표현이 reasoning 핵심 근거면 출력 X (자기 검열):
- "협력 관계", "전략적 파트너십", "사업 연관", "관련 업체"
- "수혜 기대", "관련 가능성", "협력 검토", "잠재 파트너"
- "AI 업체들", "반도체 관련주", "관련 사업" — 구체 회사명/매출 비중 없음

business_importance 정량 기준:
- 5: 매출/이익의 20%+ 의존 OR 사업 영역 단일 공급/고객 OR 50%+ 지분
- 4: 매출/이익의 10-20% 의존 OR 주력 경쟁사 (점유율 top 3) OR 20-50% 지분
- 3: 매출/이익의 5-10% 의존 OR 보조 경쟁사 OR 5-20% 지분
- < 3: 출력 X

confidence 기준:
- 0.85+ : 정량 % 또는 계약 규모를 외부 공시/연차보고서/SEC 10-K 등으로 본 적 있음
- 0.7~0.85 : 업계 well-known 사실. 정량은 모름.
- 0.6~0.7 : 알려진 사실이지만 training cutoff 후 변동 risk 있음.
- < 0.6 : 절대 출력 X. knowledge_cutoff_risk="high" 면 자동 cap 0.6.

few-shot examples:

KEEP 1 — Microsoft (MSFT):
{{
  "target_name": "OpenAI", "target_ticker": "", "target_is_public": false,
  "relation_kind": "핵심파트너", "business_importance": 5,
  "reasoning": "MS 가 OpenAI 에 130억 달러 이상 투자 (~49% 경제적 지분), Azure 가 OpenAI 의 *유일한* 클라우드 인프라. ChatGPT 사용량 증가 = Azure AI 매출 직결.",
  "knowledge_cutoff_risk": "low", "confidence": 0.92
}}
{{
  "target_name": "Apple Inc.", "target_ticker": "AAPL", "target_is_public": true,
  "relation_kind": "핵심경쟁사", "business_importance": 4,
  "reasoning": "운영체제(Windows vs macOS), 생산성(Office vs iWork), 디바이스(Surface vs iPad/Mac) 3 영역 직접 경쟁. 소비자 PC/태블릿 점유율 top 2.",
  "knowledge_cutoff_risk": "low", "confidence": 0.9
}}

REJECT 1 — vague "관련 업체":
{{
  "target_name": "AI 반도체 업체들",  ← drop (구체 회사명 없음)
  "reasoning": "AI 칩 관련 협력 가능성"  ← drop (hedge + 정량 X)
}}

REJECT 2 — speculative future:
{{
  "target_name": "비공식 협력 소문 있는 SomeCo",  ← drop (소문)
  "reasoning": "잠재적 파트너십 가능성"  ← drop (가능성)
}}

REJECT 3 — outdated, unknown if still true:
"X 인수 검토 중" / "Y 와 협력 협상 중" 같이 training cutoff 후 변경 가능 → knowledge_cutoff_risk=high → confidence cap 0.6 → 자동 drop.

엄격 규칙 요약:
1. 확실하지 않으면 빈 list. 추측 금지.
2. business_importance < 3 은 출력 X.
3. relation_kind 7종 외 금지.
4. reasoning 에 정량 근거 (% / 금액 / 지분 / 점유율 / sole source) 1개 이상 *반드시* 포함.
5. 비상장 entity (OpenAI, SpaceX, ByteDance 등) 도 포함 — 단 진짜 알 때만.
6. knowledge_cutoff_risk="high" 이면 confidence ≤ 0.6 (자동 drop).

응답 형식: {{"relations": [...]}}. JSON 1 개. 자연어 / 코드펜스 X."""


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
