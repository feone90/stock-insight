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

# 2026-05-15 — LLM 이 rationale 안에 자기 입으로 "관계 없음" 표현한 케이스
# (실제 발견: Beyond Meat 기사로 NVDA↔McDonald's complementary 박혔는데
# rationale 이 "NVDA와의 직접 관계는 없음" 명시). 명백 환상 — 자료가 자기
# 부정. 한국어 + 영어 양쪽 패턴.
_NEGATIVE_RELATION_PATTERNS: tuple[str, ...] = (
    # 한국어 (공백 제거 후 매칭 — has_target_evidence 와 같은 정규화)
    "직접관계는없",
    "직접관계없",
    "직접적인관계없",
    "관계는없음",
    "관계가없음",
    "관계없음",
    "무관함",
    "무관하다",
    "관련없",
    "직접적관계없",
    # 영어
    "nodirectrelationship",
    "nodirectrelation",
    "nodirectconnection",
    "notdirectlyrelated",
    "norelationship",
    "norelation",
    "unrelated",
)


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


def rationale_admits_no_relationship(rationale: str | None) -> bool:
    """LLM 이 rationale 에 "관계 없음" 자백한 케이스 감지.

    100% 환상 — 자료가 자기 부정. write/read/purge 모두 hard drop.
    공백/문장부호 제거 후 substring 매칭 — paraphrase 안전 (예: "직접 관계는
    없음" / "직접적인 관계는 없음" / "관계는 없음" 모두 잡힘).
    """
    if not rationale:
        return False
    # 공백 + 일부 문장부호 제거 후 lowercase. ", . - 등 제거해서 paraphrase 보강.
    normalized = "".join(rationale.split()).lower()
    for ch in (",", ".", "-", "·", "—", "–", "?", "!", "'", '"', "“", "”"):
        normalized = normalized.replace(ch, "")
    return any(p in normalized for p in _NEGATIVE_RELATION_PATTERNS)
