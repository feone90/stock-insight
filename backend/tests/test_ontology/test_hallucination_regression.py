"""Regression tests — 발견된 환상/keep 케이스 회귀 방지.

각 test 는 사용자가 prod 에서 *실제로 발견* 한 환상 / 잘못 잡힌 관계 / 또는
사용자가 *반드시* 보고 싶다고 요청한 관계 (예: MS-OpenAI) 를 박는다.

다음에 prompt 변경, evidence util 수정, purge logic 손댈 때 `uv run pytest`
가 자동 실행 → 이전 발견 case 가 옛 결과 그대로 (drop / keep) 보장.

새 환상 발견 시 → 이 파일에 test 추가 → 그게 영구 자산.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import RelationCandidate, Stock, StockRelation
from app.services.ontology.evidence import (
    has_target_evidence,
    rationale_admits_no_relationship,
)
from app.services.ontology.purge import (
    purge_cross_market_sector_match,
    purge_llm_hallucinations,
    purge_self_negating_rationales,
)


# ---------------------------------------------------------------------------
# Case 1: SK하이닉스 → 동화약품 (2026-05-14 발견)
# rationale 에 "동화약품" 0회 등장 — target evidence 부재
# ---------------------------------------------------------------------------


class TestDongwhaPharmaHallucination:
    """SK하이닉스(000660) 카드에 동화약품(000020) complementary 0.86 박혔던
    case. rationale 본문이 국토교통부/용인 클러스터 얘기인데 동화약품 등장 0회.
    """

    def test_evidence_check_drops_when_target_name_missing(self):
        rationale = (
            "기사에 'SK하이닉스, 협력사, 용인시, 한국전력, 국토교통부 등 따로 "
            "노는 구조를 하나로 묶겠다'고 명시되어 국토교통부와 용인 반도체 "
            "클러스터 추진에서 연관됨."
        )
        assert (
            has_target_evidence(rationale, "동화약품", "000020") is False
        ), "rationale 에 동화약품/000020 0회 등장 — drop 돼야 함"

    def test_evidence_check_keeps_when_target_name_present(self):
        rationale = (
            "SK하이닉스가 동화약품과 헬스케어 솔루션 분야에서 공동 개발 계약을 "
            "체결했다고 명시 — 매출 비중 X 이지만 신사업 진출 명확."
        )
        assert has_target_evidence(rationale, "동화약품", "000020") is True


# ---------------------------------------------------------------------------
# Case 2: NVDA → McDonald's (2026-05-15 발견)
# rationale 자체가 "NVDA와의 직접 관계는 없음" 자기 부정
# ---------------------------------------------------------------------------


class TestSelfNegatingRationale:
    """Beyond Meat 기사로 NVDA→McDonald's complementary 박혔던 case.
    rationale 본문이 자기 입으로 "NVDA와의 직접 관계는 없음" 자백.
    """

    def test_explicit_self_negation_detected(self):
        rationale = (
            "기사에 \"partner restaurant chains, like McDonald's\"라고 언급되며, "
            "NVDA와의 직접 관계는 없음."
        )
        assert rationale_admits_no_relationship(rationale) is True

    def test_korean_paraphrase_detected(self):
        for r in [
            "관계는 없음",
            "관계가 없음",
            "두 회사는 무관함",
            "직접적 관계 없음",
        ]:
            assert rationale_admits_no_relationship(r) is True, f"miss: {r}"

    def test_english_paraphrase_detected(self):
        for r in [
            "There is no direct relationship between the two.",
            "Not directly related per the article.",
            "The companies are unrelated.",
            "No relation between the parties.",
        ]:
            assert rationale_admits_no_relationship(r) is True, f"miss: {r}"

    def test_normal_rationale_passes(self):
        """진짜 사업 관계 명시 — drop 되면 안 됨."""
        for r in [
            "삼성전자가 SK하이닉스와 HBM3E 1,200억원 공급 계약을 체결.",
            "Apple confirmed TSMC manufactures all A18 chips.",
            "MS 가 OpenAI 에 130억 달러 투자 + Azure 독점 hosting.",
        ]:
            assert rationale_admits_no_relationship(r) is False, f"false drop: {r}"


# ---------------------------------------------------------------------------
# Case 3: Ford (F) — 1자 ticker false positive 가드
# ---------------------------------------------------------------------------


class TestSingleCharTickerSkipped:
    """Ford="F", Visa="V" 같은 1자 ticker 가 매칭 신뢰성 zero — 가드 무력화."""

    def test_one_char_ticker_passes_through(self):
        """target name "Ford", ticker "F" — 1자라 매칭 가드 skip → True 반환."""
        rationale = "Some random text without Ford or F substring matching."
        assert (
            has_target_evidence(rationale, "Ford", "F") is True
        ), "1자 ticker 만 있으면 가드 우회 (다른 가드에 의존)"


# ---------------------------------------------------------------------------
# Case 4: MS↔두산 cross-market sector_match (2026-05-15 발견)
# GICS IT bucket 공통으로 KR↔US peer 자동 생성됐던 case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_cross_market_sector_match_deletes_kr_us_peer(db):
    """US ↔ KR sector_match peer row 가 startup purge 로 삭제 (same-market 보존).

    seed 와 충돌 안 나게 가짜 ticker (TS999XX) 사용.
    """
    us_focal = Stock(ticker="TS9901", name="USFocal", market="US", sector="IT", tier=1)
    kr_target = Stock(ticker="999901", name="KRTarget", market="KOSPI", sector="IT", tier=2)
    kr_focal = Stock(ticker="999902", name="KRFocal", market="KOSPI", sector="IT", tier=1)
    db.add_all([us_focal, kr_target, kr_focal])
    await db.flush()

    db.add_all([
        # cross-market — 삭제 대상
        StockRelation(
            from_stock_id=us_focal.id, to_target="999901", to_kind="stock",
            relation_type="peer", source="sector_match",
            strength=0.5, confidence=0.4,
        ),
        # same-market — 유지 대상
        StockRelation(
            from_stock_id=kr_focal.id, to_target="999901", to_kind="stock",
            relation_type="peer", source="sector_match",
            strength=0.5, confidence=0.4,
        ),
    ])
    await db.commit()

    deleted = await purge_cross_market_sector_match(db)
    assert deleted == 1, f"cross-market row 1 개 삭제 기대, got {deleted}"

    remaining = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.source == "sector_match",
                StockRelation.from_stock_id.in_([us_focal.id, kr_focal.id]),
            )
        )
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].from_stock_id == kr_focal.id, "same-market peer 는 보존"


# ---------------------------------------------------------------------------
# Case 5: purge_self_negating_rationales 실제 DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_self_negating_rationales_deletes_row(db):
    focal = Stock(ticker="TS9911", name="Focal", market="US", sector="IT", tier=1)
    db.add(focal)
    await db.flush()

    db.add(StockRelation(
        from_stock_id=focal.id, to_target="TS9912", to_kind="stock",
        relation_type="complementary", source="news",
        strength=0.7, confidence=0.85,
        extra_metadata={
            "rationale": (
                "기사에 'partner restaurant chains, like McDonald's'라고 언급되며, "
                "TS9911과의 직접 관계는 없음."
            ),
        },
    ))
    await db.commit()

    deleted = await purge_self_negating_rationales(db)
    assert deleted == 1


# ---------------------------------------------------------------------------
# Case 6: purge_llm_hallucinations — target name 본문 부재
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_llm_hallucinations_deletes_target_absent_row(db):
    focal = Stock(ticker="999921", name="SK하이닉스미러", market="KOSPI", sector="IT", tier=1)
    target = Stock(ticker="999922", name="동화약품미러", market="KOSPI", sector="제약", tier=1)
    db.add_all([focal, target])
    await db.flush()

    db.add(StockRelation(
        from_stock_id=focal.id, to_target="999922", to_kind="stock",
        relation_type="complementary", source="news",
        strength=0.7, confidence=0.86,
        extra_metadata={
            "rationale": (
                "기사에 'SK하이닉스, 협력사, 용인시, 한국전력, 국토교통부' 명시 — "
                "국토교통부와 용인 반도체 클러스터 추진."  # 동화약품미러 0회
            ),
        },
    ))
    await db.commit()

    deleted = await purge_llm_hallucinations(db)
    assert deleted == 1


# ---------------------------------------------------------------------------
# Case 7: knowledge_relations 가 OpenAI candidate 저장 가능
# (LLM 응답을 mock 해서 persist 흐름만 검증 — 실제 LLM call 없음)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knowledge_relations_persists_openai_as_candidate(db, monkeypatch):
    """MSFT 의 knowledge_relations 가 OpenAI (비상장) 추출 시 RelationCandidate
    로 저장돼야 함 — universe 에 없어도 candidate slot 으로 보존.
    """
    from app.services.ontology import knowledge_relations as kr

    msft = Stock(ticker="TS9931", name="Microsoft Mirror", market="US", sector="IT", tier=1)
    db.add(msft)
    await db.commit()

    @pytest.fixture
    def _patch_session():
        pass

    # Mock LLM 응답 — OpenAI keep
    class _FakeAdapter:
        async def generate_json(self, prompt: str) -> str:
            import json
            return json.dumps({
                "relations": [
                    {
                        "target_name": "OpenAI",
                        "target_ticker": "",
                        "target_is_public": False,
                        "relation_kind": "핵심파트너",
                        "business_importance": 5,
                        "reasoning": (
                            "MS 가 OpenAI 에 130억 달러 이상 투자 (49% 경제적 지분), "
                            "Azure 가 OpenAI 의 유일한 클라우드 인프라. ChatGPT 사용량 "
                            "증가 = Azure AI 매출 직결."
                        ),
                        "knowledge_cutoff_risk": "low",
                        "confidence": 0.92,
                    }
                ]
            })

    monkeypatch.setattr(
        "app.services.llm.adapter.get_adapter", lambda: _FakeAdapter()
    )

    # async_session 을 test session 으로 mock
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _shared_session():
        yield db

    monkeypatch.setattr(
        "app.services.ontology.knowledge_relations.async_session", _shared_session
    )

    summary = await kr.extract_knowledge_relations("TS9931")
    assert summary.get("upserted_candidates", 0) == 1, summary

    cand = (
        await db.execute(
            select(RelationCandidate).where(
                RelationCandidate.from_ticker == "TS9931",
                RelationCandidate.source == "llm_knowledge",
            )
        )
    ).scalar_one()
    assert cand.to_ticker == "OpenAI"
    meta = cand.extra_metadata or {}
    assert meta.get("business_importance") == 5
    assert meta.get("target_is_public") is False


# ---------------------------------------------------------------------------
# Case 8: Prompt structural integrity — 핵심 instruction 살아있나
# (LLM call 없이 string-level 회귀 방지)
# ---------------------------------------------------------------------------


def test_news_prompt_has_subject_identification_gate():
    from app.services.ontology.prompts import NEWS_COMPETITOR_PROMPT
    for keyword in [
        "ARTICLE SUBJECT IDENTIFICATION",
        "Step 1",
        "Step 2",
        "Step 3",
        "svo_quote",
        "REJECT 1",  # Beyond Meat 예시
        "KEEP 1",
    ]:
        assert keyword in NEWS_COMPETITOR_PROMPT, f"missing: {keyword}"


def test_dart_prompt_has_executed_contract_gate():
    from app.services.ontology.prompts import DART_CONTRACT_PROMPT
    for keyword in [
        "FILING SUBJECT IDENTIFICATION",
        "체결",
        "검토 중",  # reject 예시
        "svo_quote",
    ]:
        assert keyword in DART_CONTRACT_PROMPT, f"missing: {keyword}"


def test_sec_8k_prompt_has_executed_agreement_gate():
    from app.services.ontology.prompts import SEC_8K_CONTRACT_PROMPT
    for keyword in [
        "FILING SUBJECT IDENTIFICATION",
        "entered into",
        "non-binding",  # reject 예시
        "svo_quote",
    ]:
        assert keyword in SEC_8K_CONTRACT_PROMPT, f"missing: {keyword}"


def test_ten_k_prompt_has_named_company_requirement():
    from app.services.ontology.prompts import TEN_K_RISK_PROMPT
    for keyword in [
        "회사 이름",
        "we face competition",  # reject 예시 (abstract)
        "svo_quote",
        "customer_concentration_pct",
    ]:
        assert keyword in TEN_K_RISK_PROMPT, f"missing: {keyword}"


def test_knowledge_prompt_requires_private_partners():
    from app.services.ontology.knowledge_relations import _PROMPT
    for keyword in [
        "비상장 핵심 파트너",
        "OpenAI",
        "Anthropic",
        "knowledge_cutoff_risk",
        "정량 근거",  # vague reasoning reject
    ]:
        assert keyword in _PROMPT, f"missing: {keyword}"
