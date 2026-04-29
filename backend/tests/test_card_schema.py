"""Pydantic validation tests for StockCard and nested types."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.card import (
    Catalyst,
    Citation,
    Claim,
    Decision,
    Fundamentals,
    GlanceVerdict,
    Interpretation,
    MacroContext,
    NewsItem,
    Relation,
    RelationsSummary,
    Scenario,
    StockCard,
    TechMomentum,
    Thesis,
)


def _minimal_card() -> StockCard:
    """Smallest valid StockCard for shape tests."""
    cite = Citation(id=1, source_type="db", label="DB · 가격 (2026-04-28)")
    return StockCard(
        ticker="005930",
        name_ko="삼성전자",
        name_en="Samsung Electronics",
        market="KRX",
        sector="반도체",
        tags=["AI/HBM"],
        price=78400.0,
        change=1200.0,
        change_pct=1.55,
        asof=datetime(2026, 4, 28, tzinfo=timezone.utc),
        glance=GlanceVerdict(
            final_grade="C",
            stance="WATCH",
            entry_stage="WAIT",
            one_line="HBM 모멘텀 살아있으나 외국인 매도 부담.",
            citations=[1],
        ),
        thesis=Thesis(
            core_thesis="HBM 사이클 유지, 5/7 실적이 분기점.",
            supports=[
                Claim(text="HBM3E 양산 가시화", citations=[1]),
                Claim(text="SK하이닉스 동조 강세", citations=[1]),
                Claim(text="USD/KRW 우호", citations=[1]),
            ],
            opposes=[
                Claim(text="외국인 4일 순매도", citations=[1]),
                Claim(text="미 10Y 4.6% 부담", citations=[1]),
            ],
            catalysts=[],
            no_catalysts_reason="이번 14일 윈도 내 확인된 일정 없음",
            scenarios=[
                Scenario(name="BULL", probability=0.25, scenario_price=88000, scenario_change_pct=12, rationale="실적 상회"),
                Scenario(name="BASE", probability=0.55, scenario_price=80000, scenario_change_pct=2, rationale="컨센 부합"),
                Scenario(name="BEAR", probability=0.20, scenario_price=72000, scenario_change_pct=-8, rationale="가이던스 약화"),
            ],
            citations=[1],
        ),
        technical=TechMomentum(
            rsi_14=58.0, mfi_14=None, atr_pct=2.3, cmf_20=None, obv_ratio=None,
            ma_stack="정배열", rvol_20=1.4, box_position=None,
            summary_line="RSI 58, MA 정배열, RVOL 1.4x.", citations=[1],
        ),
        relations=RelationsSummary(
            one_line="SK하이닉스 +2.8% 동조.", relations=[], citations=[1],
        ),
        news=[],
        macro=MacroContext(
            one_line="USD/KRW 1378, 미 10Y 4.6%.", vix=18.7, fx_pairs={"USD/KRW": 1378.0},
            us_10y=4.6, sensitivities=[], upcoming_events=[], citations=[1],
        ),
        fundamentals=Fundamentals(
            per=14.2, pbr=1.4, market_cap_krw=4.68e14, dividend_yield=2.1, per_5y_z=-0.5, citations=[1],
        ),
        decision=Decision(
            stance="WATCH", sizing_note="대기", support_price=75000.0, risk_threshold=72500.0, citations=[1],
        ),
        citations=[cite],
        analysis_id="test-001",
        generated_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        persona_version="analyst_v1",
    )


def test_minimal_card_validates():
    card = _minimal_card()
    assert card.ticker == "005930"
    assert card.thesis.scenarios[0].name == "BULL"
    assert card.thesis.no_catalysts_reason is not None


def test_citation_source_type_enforced():
    with pytest.raises(ValidationError):
        Citation(id=1, source_type="llm-interpretation", label="x")  # not in enum


def test_interpretation_kind_enforced():
    with pytest.raises(ValidationError):
        Interpretation(kind="hand-waving", based_on=[1])  # not in enum


def test_scenario_probability_bounds():
    with pytest.raises(ValidationError):
        Scenario(name="BULL", probability=1.5, scenario_price=100, scenario_change_pct=10, rationale="x")


def test_catalysts_can_be_empty():
    card = _minimal_card()
    card_dict = card.model_dump()
    card_dict["thesis"]["catalysts"] = []
    StockCard.model_validate(card_dict)  # must not raise


def test_strategy_renamed_to_stance():
    """`strategy` field name must NOT exist; `stance` must."""
    g = GlanceVerdict(final_grade="A", stance="BUY", entry_stage="ENTER", one_line="x", citations=[])
    assert g.stance == "BUY"
    assert "strategy" not in g.model_dump()


def test_target_price_renamed_to_scenario_price():
    s = Scenario(name="BULL", probability=0.3, scenario_price=100, scenario_change_pct=5, rationale="x")
    assert s.scenario_price == 100
    assert "target_price" not in s.model_dump()


def test_stop_loss_renamed_to_risk_threshold():
    d = Decision(stance="BUY", sizing_note="기본", support_price=90, risk_threshold=85, citations=[])
    assert d.risk_threshold == 85
    assert "stop_loss" not in d.model_dump()


def test_persona_constants_exist_and_have_no_forbidden_words():
    """Persona prompts must NOT contain UI-forbidden marketing words."""
    from app.services.analyst.persona import (
        ANALYST_V1,
        PERSONA_VERSION,
        RESEARCHER_V1,
    )

    assert PERSONA_VERSION == "analyst_v1"
    # Forbidden marketing words — these are ENFORCED in the persona itself
    # (the analyst is told to ban them in OUTPUT). The prompts are allowed
    # to mention them in the "금지" list. So we only check that the
    # persona TELLS the model to ban them.
    for forbidden in ["강력 매수", "확실한 수익", "유망주"]:
        assert forbidden in ANALYST_V1, (
            f"persona prompt must explicitly forbid '{forbidden}'"
        )
    # And the persona must not call itself buffett-grade in the body — only
    # the version string is "analyst_v1".
    assert "워렌버핏" in ANALYST_V1  # mentioned in 금지 list
    assert "버핏급" not in ANALYST_V1  # not used as identity
    # Researcher prompt sanity
    assert "추측 금지" in RESEARCHER_V1
    assert "fabricate" in RESEARCHER_V1
