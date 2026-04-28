"""End-to-end engine wrapper tests with mocked stages."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import Stock
from app.models.analysis import Analysis
from app.schemas.card import StockCard
from app.services.analyst.engine import analyze


def _build_card(ticker: str = "ENG1") -> StockCard:
    """Build a StockCard with valid minimum data — used as fake synthesizer output."""
    return StockCard.model_validate({
        "ticker": ticker,
        "name_ko": "엔진테스트",
        "name_en": "Engine Test",
        "market": "KRX",
        "sector": "기타",
        "tags": [],
        "price": 100.0,
        "change": 0.0,
        "change_pct": 0.0,
        "asof": "2026-04-28T00:00:00+00:00",
        "glance": {
            "final_grade": "B",
            "stance": "WATCH",
            "entry_stage": "WAIT",
            "one_line": "minimal one_line for engine test",
            "citations": [],
        },
        "thesis": {
            "core_thesis": "minimal core thesis for engine test",
            "supports": [
                {"text": "a", "citations": []},
                {"text": "b", "citations": []},
                {"text": "c", "citations": []},
            ],
            "opposes": [
                {"text": "x", "citations": []},
                {"text": "y", "citations": []},
            ],
            "catalysts": [],
            "no_catalysts_reason": "test",
            "scenarios": [
                {"name": "BULL", "probability": 0.3, "scenario_price": 110, "scenario_change_pct": 10, "rationale": "x"},
                {"name": "BASE", "probability": 0.5, "scenario_price": 100, "scenario_change_pct": 0, "rationale": "x"},
                {"name": "BEAR", "probability": 0.2, "scenario_price": 90, "scenario_change_pct": -10, "rationale": "x"},
            ],
            "citations": [],
        },
        "technical": {
            "rsi_14": None, "mfi_14": None, "atr_pct": None, "cmf_20": None,
            "obv_ratio": None, "ma_stack": None, "rvol_20": None,
            "box_position": None, "summary_line": "", "citations": [],
        },
        "relations": {"one_line": "", "relations": [], "citations": []},
        "news": [],
        "macro": {
            "one_line": "", "vix": None, "fx_pairs": {}, "us_10y": None,
            "sensitivities": [], "upcoming_events": [], "citations": [],
        },
        "fundamentals": {
            "per": None, "pbr": None, "market_cap_krw": None,
            "dividend_yield": None, "per_5y_z": None, "citations": [],
        },
        "decision": {
            "stance": "WATCH", "sizing_note": "대기", "support_price": None,
            "risk_threshold": None, "citations": [],
        },
        "citations": [],
        "analysis_id": "eng-1",
        "generated_at": "2026-04-28T00:00:00+00:00",
        "persona_version": "analyst_v1",
    })


@pytest_asyncio.fixture
async def db_for_engine(db, monkeypatch):
    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("app.services.analyst.engine.async_session", _session)
    return db


@pytest.mark.asyncio
async def test_analyze_persists_card_to_analyses_table(db_for_engine, monkeypatch):
    db = db_for_engine
    s = Stock(ticker="ENG1", name="엔진테스트", market="KRX", sector="기타")
    db.add(s)
    await db.commit()

    monkeypatch.setattr(
        "app.services.analyst.engine.run_research",
        AsyncMock(return_value={"findings": [], "citations": []}),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.run_synthesize",
        AsyncMock(return_value=_build_card("ENG1")),
    )

    out = await analyze("ENG1")
    assert out.ticker == "ENG1"

    rows = (
        await db.execute(select(Analysis).where(Analysis.stock_id == s.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].schema_version == "v2"
    assert rows[0].persona_version == "analyst_v1"
    assert rows[0].card_data["ticker"] == "ENG1"


@pytest.mark.asyncio
async def test_analyze_upserts_when_same_day_row_exists(db_for_engine, monkeypatch):
    db = db_for_engine
    from datetime import date as _date

    s = Stock(ticker="ENG2", name="x", market="KRX", sector="x")
    db.add(s)
    await db.flush()
    db.add(
        Analysis(
            stock_id=s.id,
            date=_date.today(),
            period_type="daily",
            summary="old",
            feedback="old",
            schema_version="v1",
        )
    )
    await db.commit()

    monkeypatch.setattr(
        "app.services.analyst.engine.run_research",
        AsyncMock(return_value={"findings": []}),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.run_synthesize",
        AsyncMock(return_value=_build_card("ENG2")),
    )

    await analyze("ENG2")

    rows = (
        await db.execute(select(Analysis).where(Analysis.stock_id == s.id))
    ).scalars().all()
    assert len(rows) == 1  # upserted, not appended
    assert rows[0].schema_version == "v2"
    assert rows[0].card_data["ticker"] == "ENG2"
