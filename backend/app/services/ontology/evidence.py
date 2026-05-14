"""Shared hallucination-evidence check for LLM-extracted relations.

Used by:
  - `validator.validate_and_route` (write path — drop on insert)
  - `admin.purge_ontology_noise` (cleanup path — delete existing rows)
  - `data_layer._fetch_relations_data` (card read path — hide + soft-delete)
  - `api.ontology._outgoing` (graph read path — hide + soft-delete)

2026-05-14 발견 케이스 (SK하이닉스→동화약품 complementary 0.86):
    rationale = "기사에 'SK하이닉스, 협력사, 용인시, 한국전력, 국토교통부 등
                 따로 노는 구조를 하나로 묶겠다'고 명시되어 국토교통부와
                 용인 반도체 클러스터 추진에서 연관됨."
    → "동화약품" 0회 등장 + ticker "000020" 0회 등장. 명백한 LLM 환상.

이 가드를 모든 read path 에 적용해서, 옛 row 가 DB 에 남아도 사용자 화면
에는 안 보이게 (defense in depth at every layer). 추가로 read path 에서
hallucination 감지 시 fire-and-forget `is_active=False` 로 soft-delete →
DB 도 자기 청소.
"""
from __future__ import annotations

LLM_SOURCES_REQUIRING_EVIDENCE = frozenset({
    "news", "sec_8k", "sec_10k_risk", "dart_contract", "llm_web_search",
})


def _normalize(text: str) -> str:
    """공백 제거 + lowercase. 한글 띄어쓰기 edge case ("SK 하이닉스" vs
    "SK하이닉스") 대응."""
    return "".join(text.split()).lower()


def has_target_evidence(
    rationale: str | None, target_name: str | None, to_ticker: str | None
) -> bool:
    """Stock.name OR ticker 중 하나가 rationale 에 substring 등장하면 True.

    둘 다 1 자 이하면 매칭 신뢰성 zero 라 가드 우회 — `True` 반환 (다른 가드
    [rationale 30+ chars, confidence floor] 에 의존). production 에서 1 자
    ticker (Ford="F" 등) 는 false positive 거의 항상 통과해 가드 효과 없음.
    """
    rat_norm = _normalize(rationale or "")
    name_norm = _normalize(target_name or "")
    ticker_norm = _normalize(to_ticker or "")
    candidates = [c for c in (name_norm, ticker_norm) if len(c) >= 2]
    if not candidates:
        return True  # 가드 무력화
    return any(c in rat_norm for c in candidates)


def is_llm_source(source: str | None) -> bool:
    return source in LLM_SOURCES_REQUIRING_EVIDENCE
