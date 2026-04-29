"""Adversarial tests — LLM mis-output triggers retry or surfaces ValueError."""
import json
from unittest.mock import AsyncMock

import pytest

from app.services.analyst.synthesize import run_synthesize


def _good_dict() -> dict:
    return {
        "glance": {
            "final_grade": "C", "stance": "WATCH", "entry_stage": "WAIT",
            "one_line": "ok", "citations": [1],
        },
        "thesis": {
            "core_thesis": "ok",
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
            "no_catalysts_reason": "none",
            "scenarios": [
                {"name": "BULL", "probability": 0.25, "scenario_price": 110, "scenario_change_pct": 10, "rationale": "x"},
                {"name": "BASE", "probability": 0.55, "scenario_price": 100, "scenario_change_pct": 0, "rationale": "x"},
                {"name": "BEAR", "probability": 0.20, "scenario_price": 90, "scenario_change_pct": -10, "rationale": "x"},
            ],
            "citations": [1],
        },
        "relations_narrative": {"one_line": "ok", "notes_by_target": {}, "citations": []},
        "decision": {
            "stance": "WATCH", "sizing_note": "대기",
            "support_price": 95, "risk_threshold": 85, "citations": [1],
        },
        "interp_citations": [{"id": 1, "source_type": "web", "label": "x"}],
    }


@pytest.mark.asyncio
async def test_too_few_supports_triggers_retry_then_succeeds(monkeypatch):
    bad = _good_dict()
    bad["thesis"]["supports"] = [{"text": "only-one", "citations": []}]  # < 3
    good = _good_dict()

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(side_effect=[json.dumps(bad), json.dumps(good)])
    monkeypatch.setattr(
        "app.services.analyst.synthesize.get_analyst_adapter", lambda: adapter
    )

    out = await run_synthesize("X", {"findings": []}, max_retries=1)
    assert len(out.thesis.supports) >= 3
    assert adapter.generate_json.await_count == 2


@pytest.mark.asyncio
async def test_scenario_probabilities_can_drift_only_slightly(monkeypatch):
    """The schema doesn't force probability sum; the smoke test does. Here we
    confirm that out-of-bounds individual probabilities (>1) bounce."""
    bad = _good_dict()
    bad["thesis"]["scenarios"][0]["probability"] = 1.5  # invalid (>1)
    good = _good_dict()

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(side_effect=[json.dumps(bad), json.dumps(good)])
    monkeypatch.setattr(
        "app.services.analyst.synthesize.get_analyst_adapter", lambda: adapter
    )
    out = await run_synthesize("X", {"findings": []}, max_retries=1)
    assert all(0 <= s.probability <= 1 for s in out.thesis.scenarios)


@pytest.mark.asyncio
async def test_only_two_scenarios_triggers_retry(monkeypatch):
    bad = _good_dict()
    bad["thesis"]["scenarios"] = bad["thesis"]["scenarios"][:2]  # missing BEAR
    good = _good_dict()

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(side_effect=[json.dumps(bad), json.dumps(good)])
    monkeypatch.setattr(
        "app.services.analyst.synthesize.get_analyst_adapter", lambda: adapter
    )
    out = await run_synthesize("X", {"findings": []}, max_retries=1)
    assert len(out.thesis.scenarios) == 3


@pytest.mark.asyncio
async def test_garbage_json_after_retries_raises(monkeypatch):
    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(
        side_effect=["not even json", "still not json"]
    )
    monkeypatch.setattr(
        "app.services.analyst.synthesize.get_analyst_adapter", lambda: adapter
    )
    with pytest.raises(ValueError, match="synthesize failed"):
        await run_synthesize("X", {"findings": []}, max_retries=1)


@pytest.mark.asyncio
async def test_extra_data_layer_fields_are_ignored(monkeypatch):
    """LLM still echoes technical/macro/etc. — Pydantic ignores extras gracefully."""
    payload = _good_dict()
    payload["technical"] = {"rsi_14": 999}  # data field LLM should not produce
    payload["macro"] = {"vix": 99}

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr(
        "app.services.analyst.synthesize.get_analyst_adapter", lambda: adapter
    )
    out = await run_synthesize("X", {"findings": []})
    assert hasattr(out, "glance")
    assert not hasattr(out, "technical")  # AnalystOutput has no technical
