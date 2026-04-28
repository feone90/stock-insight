"""Stage 2 synthesizer tests with mocked adapter.

After the data/analyst split, `run_synthesize` returns `AnalystOutput`
(NOT `StockCard`). The 4 LLM-judgment fields only — data fields
come from `data_layer` and are merged at `engine.compose`.
"""
import json
from unittest.mock import AsyncMock

import pytest

from app.schemas.card import AnalystOutput
from app.services.analyst.synthesize import (
    PROMPT_SIZE_SOFT_LIMIT,
    _build_prompt,
    run_synthesize,
)


def _valid_analyst_dict() -> dict:
    """Minimum-valid AnalystOutput shape — only the 4 LLM fields."""
    return {
        "glance": {
            "final_grade": "C",
            "stance": "WATCH",
            "entry_stage": "WAIT",
            "one_line": "HBM 모멘텀 살아있으나 외국인 매도 부담",
            "citations": [1],
        },
        "thesis": {
            "core_thesis": "HBM 사이클 유지",
            "supports": [
                {"text": "a", "citations": [1]},
                {"text": "b", "citations": [1]},
                {"text": "c", "citations": [1]},
            ],
            "opposes": [
                {"text": "x", "citations": [1]},
                {"text": "y", "citations": [1]},
            ],
            "catalysts": [],
            "no_catalysts_reason": "윈도 내 일정 없음",
            "scenarios": [
                {"name": "BULL", "probability": 0.25, "scenario_price": 88000, "scenario_change_pct": 12, "rationale": "x"},
                {"name": "BASE", "probability": 0.55, "scenario_price": 80000, "scenario_change_pct": 2, "rationale": "x"},
                {"name": "BEAR", "probability": 0.20, "scenario_price": 72000, "scenario_change_pct": -8, "rationale": "x"},
            ],
            "citations": [1],
        },
        "relations_narrative": {
            "one_line": "SK하이닉스 동조 강세",
            "notes_by_target": {"000660": "HBM 동조 수혜"},
            "citations": [1],
        },
        "decision": {
            "stance": "WATCH",
            "sizing_note": "대기",
            "support_price": 75000,
            "risk_threshold": 72500,
            "citations": [1],
        },
        "interp_citations": [
            {"id": 1, "source_type": "web", "label": "분석가 도입 출처"},
        ],
    }


@pytest.mark.asyncio
async def test_synthesize_returns_analyst_output(monkeypatch):
    payload = _valid_analyst_dict()
    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr(
        "app.services.analyst.synthesize.get_analyst_adapter", lambda: adapter
    )

    out = await run_synthesize(ticker="005930", research={"findings": []})
    assert isinstance(out, AnalystOutput)
    assert out.glance.stance == "WATCH"
    assert out.thesis.no_catalysts_reason == "윈도 내 일정 없음"
    assert out.relations_narrative.notes_by_target["000660"] == "HBM 동조 수혜"
    assert out.decision.support_price == 75000


@pytest.mark.asyncio
async def test_synthesize_retries_on_validation_error(monkeypatch):
    bad = {"glance": {"stance": "WATCH"}}  # missing required fields
    good = _valid_analyst_dict()

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(
        side_effect=[json.dumps(bad), json.dumps(good)]
    )
    monkeypatch.setattr(
        "app.services.analyst.synthesize.get_analyst_adapter", lambda: adapter
    )

    out = await run_synthesize(
        ticker="005930", research={"findings": []}, max_retries=1
    )
    assert isinstance(out, AnalystOutput)
    assert adapter.generate_json.await_count == 2


@pytest.mark.asyncio
async def test_synthesize_raises_after_exhausted_retries(monkeypatch):
    bad = {"glance": {"stance": "WATCH"}}

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(
        side_effect=[json.dumps(bad), json.dumps(bad)]
    )
    monkeypatch.setattr(
        "app.services.analyst.synthesize.get_analyst_adapter", lambda: adapter
    )

    with pytest.raises(ValueError, match="synthesize failed"):
        await run_synthesize(
            ticker="005930", research={"findings": []}, max_retries=1
        )


def test_prompt_size_under_soft_limit():
    """Spec §11 — synthesizer prompt size ≤ 18KB. Asserted with a representative
    research blob (~14KB cap from synthesize module)."""
    research = {
        "findings": [{"key": "k", "value": "v" * 200} for _ in range(50)],
        "citations": [{"id": i, "source_type": "db", "label": "x"} for i in range(20)],
        "gaps_noted": [],
    }
    prompt = _build_prompt("005930", research)
    size = len(prompt.encode("utf-8"))
    assert size <= PROMPT_SIZE_SOFT_LIMIT, (
        f"prompt size {size} exceeds soft limit {PROMPT_SIZE_SOFT_LIMIT}"
    )
