"""2-pass LLM verifier — rationale 이 실제 비즈니스 관계 주장 인지 검증.

옛 substring 가드 (evidence.py) 의 한계:
  - "직접관계는없" 만 잡고 "직접적인 관계까지는 아니지만 ~" 같은 paraphrase 못 잡음
  - "관련 가능성", "수혜 기대" 같은 hedge 추측 통과
  - "같이 언급됨", "비교 대상" 같은 mention-only 통과

이 verifier 는 첫 추출 LLM 출력을 두 번째 LLM 이 검증 — 의미 단위. batch
로 한 번에 처리해서 비용/지연 ↓ (관계 N 개 → LLM 호출 1회 ~$0.005-0.01).

호출처:
  - extract_news (validate_and_route 호출 전)
  - extract_sec, dart_contract, knowledge_relations (선택적)

실패 정책: LLM 호출 자체 실패 시 fallback 으로 *통과* (extraction 흐름 안
깸). substring 가드 + validator 등 다른 layer 가 boundary. 매우 보수적
verifier 동작은 false negative (진짜 관계 drop) 위험 ↑.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from app.services.ontology.schemas import ExtractedRelation

logger = logging.getLogger(__name__)

Verdict = Literal["keep", "drop"]

_VERIFY_PROMPT = """다음은 1차 LLM 이 뉴스/공시 본문에서 추출한 "회사 A → 회사 B 비즈니스 관계" 후보 목록이다. 각 후보의 rationale 이 *실제로* 비즈니스 관계 (계약/공급/매수/경쟁/투자/모자회사) 를 명시적으로 *주장* 하는지 판단하라.

drop 조건 (해당 시 verdict="drop"):
- 자기 부정: "관계 없음", "직접 관계 X", "관련 없음", "직접적이지 않음"
- Hedge/추측: "관련 가능성", "수혜 기대", "주목받는", "협력 검토 중", "협력 가능성"
- Mention-only: "같이 언급됨", "비교 대상", "예시로 들음"
- 단순 동질성: 같은 섹터/시장이라는 이유만
- 두루뭉술: 구체적 매출/계약/지분 % 없이 "협력 관계" 같은 막연 표현
- 인용만: 본문 한 줄 인용했지만 두 회사 사이 비즈니스 관계 주장 안 함

keep 조건:
- 구체적 사실: "X 가 Y 에 N억 공급", "X 가 Y 의 N% 지분 보유"
- 명시적 분류: "X 는 Y 의 핵심 경쟁사", "X 는 Y 의 모회사"
- 정량 의존: "Y 매출의 N% 가 X 향"

각 후보마다 1 줄 reason + verdict.

후보들:
{candidates_block}

응답 JSON 1 개 — 자연어 / 코드펜스 X:
{{"verdicts": [{{"index": 0, "verdict": "keep" or "drop", "reason": "..."}}, ...]}}"""


def _format_candidate(idx: int, rel: ExtractedRelation) -> str:
    rationale = (rel.rationale or "").strip()
    if not rationale and isinstance(rel.extra_metadata, dict):
        rationale = (rel.extra_metadata.get("rationale") or "").strip()
    rationale = rationale[:600]  # 너무 긴 건 잘라 token 절약
    return (
        f"[{idx}] {rel.from_ticker} → {rel.to_ticker} "
        f"(type={rel.relation_type}, signal={rel.signal_direction})\n"
        f"rationale: {rationale or '(empty)'}"
    )


async def verify_rationales(
    candidates: list[ExtractedRelation],
) -> list[ExtractedRelation]:
    """LLM batch verify. drop 판정된 후보 제외 후 남은 list 반환.

    실패 / 응답 이상 시 원본 그대로 반환 (boundary 안전).
    """
    if not candidates:
        return candidates
    candidates_block = "\n\n".join(
        _format_candidate(i, r) for i, r in enumerate(candidates)
    )
    prompt = _VERIFY_PROMPT.format(candidates_block=candidates_block)

    try:
        from app.services.llm.adapter import get_adapter

        raw = await get_adapter().generate_json(prompt)
    except Exception as e:  # noqa: BLE001
        logger.warning("rationale_verifier LLM call failed: %s — pass-through", e)
        return candidates

    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as e:
        logger.warning("rationale_verifier parse failed: %s — pass-through", e)
        return candidates
    if not isinstance(parsed, dict):
        return candidates
    verdicts_raw = parsed.get("verdicts") or []
    if not isinstance(verdicts_raw, list):
        return candidates

    drop_indices: set[int] = set()
    for v in verdicts_raw:
        if not isinstance(v, dict):
            continue
        try:
            idx = int(v.get("index"))
        except (TypeError, ValueError):
            continue
        verdict = (v.get("verdict") or "").strip().lower()
        if verdict == "drop" and 0 <= idx < len(candidates):
            drop_indices.add(idx)
            rel = candidates[idx]
            logger.info(
                "rationale_verifier drop %s→%s type=%s reason=%r",
                rel.from_ticker, rel.to_ticker, rel.relation_type,
                str(v.get("reason"))[:120],
            )

    if not drop_indices:
        return candidates
    return [r for i, r in enumerate(candidates) if i not in drop_indices]
