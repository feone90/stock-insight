"""Stage 2 synthesizer tests with mocked adapter."""
import json
from unittest.mock import AsyncMock

import pytest

from app.schemas.card import StockCard
from app.services.analyst.synthesize import run_synthesize


def _valid_card_dict() -> dict:
    return {
        "ticker": "005930",
        "name_ko": "삼성전자",
        "name_en": "Samsung Electronics",
        "market": "KRX",
        "sector": "반도체",
        "tags": ["AI/HBM"],
        "price": 78400.0,
        "change": 1200.0,
        "change_pct": 1.55,
        "asof": "2026-04-28T00:00:00+00:00",
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
        "technical": {
            "rsi_14": 58, "mfi_14": None, "atr_pct": 2.3, "cmf_20": None, "obv_ratio": None,
            "ma_stack": "정배열", "rvol_20": 1.4, "box_position": None,
            "summary_line": "RSI 58 정배열", "citations": [1],
        },
        "relations": {"one_line": "x", "relations": [], "citations": [1]},
        "news": [],
        "macro": {
            "one_line": "x", "vix": 18.7, "fx_pairs": {"USD/KRW": 1378.0}, "us_10y": 4.6,
            "sensitivities": [], "upcoming_events": [], "citations": [1],
        },
        "fundamentals": {
            "per": 14.2, "pbr": 1.4, "market_cap_krw": 4.68e14,
            "dividend_yield": 2.1, "per_5y_z": -0.5, "citations": [1],
        },
        "decision": {
            "stance": "WATCH", "sizing_note": "대기", "support_price": 75000,
            "risk_threshold": 72500, "citations": [1],
        },
        "citations": [{"id": 1, "source_type": "db", "label": "DB · 가격"}],
        "analysis_id": "test-1",
        "generated_at": "2026-04-28T00:00:00+00:00",
        "persona_version": "analyst_v1",
    }


@pytest.mark.asyncio
async def test_synthesize_returns_validated_stock_card(monkeypatch):
    fake_card_dict = _valid_card_dict()
    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(return_value=json.dumps(fake_card_dict))
    monkeypatch.setattr(
        "app.services.analyst.synthesize._adapter", lambda: adapter
    )

    research_result = {"findings": [{"k": "v"}], "citations": []}
    card = await run_synthesize(ticker="005930", research=research_result)
    assert isinstance(card, StockCard)
    assert card.glance.stance == "WATCH"
    assert card.thesis.no_catalysts_reason == "윈도 내 일정 없음"
    assert card.thesis.catalysts == []


@pytest.mark.asyncio
async def test_synthesize_retries_on_validation_error(monkeypatch):
    """First response is invalid; second is valid → returns card after retry."""
    bad = {"ticker": "X"}  # missing required fields
    good = _valid_card_dict()

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(
        side_effect=[json.dumps(bad), json.dumps(good)]
    )
    monkeypatch.setattr(
        "app.services.analyst.synthesize._adapter", lambda: adapter
    )

    card = await run_synthesize(
        ticker="005930", research={"findings": []}, max_retries=1
    )
    assert isinstance(card, StockCard)
    assert adapter.generate_json.await_count == 2


@pytest.mark.asyncio
async def test_synthesize_raises_after_exhausted_retries(monkeypatch):
    """Two bad responses → raises ValueError."""
    bad = {"ticker": "X"}

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(
        side_effect=[json.dumps(bad), json.dumps(bad)]
    )
    monkeypatch.setattr(
        "app.services.analyst.synthesize._adapter", lambda: adapter
    )

    with pytest.raises(ValueError, match="synthesize failed"):
        await run_synthesize(
            ticker="005930", research={"findings": []}, max_retries=1
        )


@pytest.mark.asyncio
async def test_synthesize_overrides_persona_version_to_server_value(monkeypatch):
    """Even if LLM emits a wrong persona_version, server forces analyst_v1."""
    card_dict = _valid_card_dict()
    card_dict["persona_version"] = "rogue_v99"

    adapter = AsyncMock()
    adapter.generate_json = AsyncMock(return_value=json.dumps(card_dict))
    monkeypatch.setattr(
        "app.services.analyst.synthesize._adapter", lambda: adapter
    )

    card = await run_synthesize(ticker="005930", research={})
    assert card.persona_version == "analyst_v1"
