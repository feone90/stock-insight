"""Property-style tests for `compose` citation invariants.

Hand-fuzzed (no `hypothesis` dep). For random valid (DataLayer, AnalystOutput)
pairs we assert:
  1. Every nested `citations: list[int]` references the final pool.
  2. Final pool IDs are 1..N contiguous (no gaps).
  3. Final pool size equals sum of input layer citation counts (no double-count
     and no drop).
"""
import random
from datetime import datetime, timezone

import pytest

from app.schemas.card import (
    AnalystOutput,
    Citation,
    Claim,
    DataLayer,
    Decision,
    Fundamentals,
    GlanceVerdict,
    MacroContext,
    Relation,
    RelationsNarrative,
    Scenario,
    TechMomentum,
    Thesis,
)
from app.services.analyst.engine import compose


def _fuzz_layers(seed: int) -> tuple[DataLayer, AnalystOutput]:
    """Build a (DataLayer, AnalystOutput) pair with seed-driven citation counts."""
    rng = random.Random(seed)
    k = rng.randint(0, 5)
    m = rng.randint(0, 4)

    data_citations = [
        Citation(id=i + 1, source_type="db", label=f"data#{i+1}")
        for i in range(k)
    ]
    interp_citations = [
        Citation(id=i + 1, source_type="web", label=f"analyst#{i+1}")
        for i in range(m)
    ]

    def pick_data_ids(n: int) -> list[int]:
        if k == 0 or n == 0:
            return []
        return [rng.randint(1, k) for _ in range(n)]

    def pick_analyst_ids(n: int) -> list[int]:
        if m == 0 or n == 0:
            return []
        return [rng.randint(1, m) for _ in range(n)]

    technical = (
        TechMomentum(
            rsi_14=50.0, mfi_14=None, atr_pct=2.0, cmf_20=None, obv_ratio=None,
            ma_stack=None, rvol_20=None, box_position=None,
            summary_line="x", citations=pick_data_ids(rng.randint(0, k)),
        )
        if k > 0
        else None
    )
    macro = (
        MacroContext(
            one_line="x", vix=None, fx_pairs={}, us_10y=None,
            sensitivities=[], upcoming_events=[],
            citations=pick_data_ids(rng.randint(0, k)),
        )
        if k > 0
        else None
    )
    fundamentals = Fundamentals(citations=pick_data_ids(rng.randint(0, k)) if k else [])

    relations_data: list[Relation] = []
    for _ in range(rng.randint(0, 3)):
        relations_data.append(
            Relation(
                target_ticker=f"T{rng.randint(0, 9999):04d}",
                target_name="x",
                relation_type="peer",
                strength=rng.random(),
                today_change_pct=None,
                notes=None,
                citation_ids=pick_data_ids(rng.randint(0, k)),
            )
        )

    data = DataLayer(
        technical=technical,
        macro=macro,
        fundamentals=fundamentals,
        news=[],
        relations_data=relations_data,
        data_citations=data_citations,
    )

    glance = GlanceVerdict(
        final_grade="C", stance="WATCH", entry_stage="WAIT",
        one_line="x", citations=pick_analyst_ids(rng.randint(0, m)),
    )
    thesis = Thesis(
        core_thesis="x",
        supports=[
            Claim(text=f"s{i}", citations=pick_analyst_ids(rng.randint(0, m)))
            for i in range(3)
        ],
        opposes=[
            Claim(text=f"o{i}", citations=pick_analyst_ids(rng.randint(0, m)))
            for i in range(2)
        ],
        catalysts=[],
        no_catalysts_reason="x",
        scenarios=[
            Scenario(name="BULL", probability=0.25, scenario_price=None, scenario_change_pct=None, rationale="x"),
            Scenario(name="BASE", probability=0.55, scenario_price=None, scenario_change_pct=None, rationale="x"),
            Scenario(name="BEAR", probability=0.20, scenario_price=None, scenario_change_pct=None, rationale="x"),
        ],
        citations=pick_analyst_ids(rng.randint(0, m)),
    )
    decision = Decision(
        stance="WATCH", sizing_note="대기",
        support_price=None, risk_threshold=None,
        citations=pick_analyst_ids(rng.randint(0, m)),
    )
    narrative = RelationsNarrative(
        one_line="x",
        notes_by_target={r.target_ticker: "n" for r in relations_data},
        citations=pick_analyst_ids(rng.randint(0, m)),
    )

    analyst = AnalystOutput(
        glance=glance,
        thesis=thesis,
        relations_narrative=narrative,
        decision=decision,
        interp_citations=interp_citations,
    )
    return data, analyst


def _identity() -> dict:
    return {
        "ticker": "TEST", "name_ko": "x", "name_en": "x", "market": "KRX",
        "sector": "x", "tags": [], "price": 1.0, "change": 0.0, "change_pct": 0.0,
        "asof": datetime(2026, 4, 28, tzinfo=timezone.utc),
    }


@pytest.mark.parametrize("seed", list(range(20)))
def test_compose_invariants_over_random_inputs(seed: int):
    data, analyst = _fuzz_layers(seed)
    card = compose("TEST", data, analyst, _identity())

    final_ids = {c.id for c in card.citations}
    expected_size = len(data.data_citations) + len(analyst.interp_citations)

    # Invariant 1: contiguous 1..N
    assert sorted(final_ids) == list(range(1, expected_size + 1))

    # Invariant 2: total count equals sum of input pools (no double-count)
    assert len(card.citations) == expected_size

    # Invariant 3: every nested citations: list[int] is a subset of final_ids
    referenced: set[int] = set()
    referenced.update(card.glance.citations)
    referenced.update(card.thesis.citations)
    for c in card.thesis.supports:
        referenced.update(c.citations)
    for c in card.thesis.opposes:
        referenced.update(c.citations)
    for cat in card.thesis.catalysts:
        referenced.update(cat.citation_ids)
    referenced.update(card.decision.citations)
    referenced.update(card.relations.citations)
    for rel in card.relations.relations:
        referenced.update(rel.citation_ids)
    referenced.update(card.technical.citations)
    referenced.update(card.macro.citations)
    referenced.update(card.fundamentals.citations)
    for n in card.news:
        referenced.add(n.citation_id)

    dangling = referenced - final_ids
    assert not dangling, f"seed={seed} dangling refs: {dangling}"


def test_compose_offset_preserves_data_ids_and_shifts_analyst_ids():
    data, analyst = _fuzz_layers(seed=42)
    if not data.data_citations or not analyst.interp_citations:
        pytest.skip("seed produced empty pool — pick another scenario")
    k = len(data.data_citations)

    # Capture the analyst id that glance references (if any) before compose.
    original_glance = list(analyst.glance.citations)
    card = compose("TEST", data, analyst, _identity())

    # Data citations keep their IDs (1..K); analyst IDs become K+1..K+M.
    final_ids = sorted(c.id for c in card.citations)
    assert final_ids[:k] == list(range(1, k + 1))
    assert final_ids[k:] == list(range(k + 1, k + 1 + len(analyst.interp_citations)))

    # Verify glance shift if it had any analyst refs
    if original_glance:
        assert all(cid > k for cid in card.glance.citations)
