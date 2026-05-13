"""Engine + compose tests for the refactored data/analyst split flow."""
import asyncio
from contextlib import asynccontextmanager
from datetime import date as _date
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import PriceHistory, Stock
from app.models.analysis import Analysis, KeywordDetail
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
    StockCard,
    TechMomentum,
    Thesis,
)
from app.services.analyst.engine import _TICKER_LOCKS, _get_ticker_lock, analyze, compose


def _seed_price_history(db, stock_id: int, days: int = 1) -> None:
    """Minimum history so `is_analyzable` passes."""
    for i in range(days):
        db.add(
            PriceHistory(
                stock_id=stock_id,
                date=_date.today(),
                open=100,
                high=101,
                low=99,
                close=100,
                volume=1000,
            )
        )


def _identity(ticker: str = "ENG1") -> dict:
    return {
        "ticker": ticker,
        "name_ko": "엔진테스트",
        "name_en": "Engine Test",
        "market": "KRX",
        "sector": "기타",
        "tags": [],
        "price": 100.0,
        "change": 0.0,
        "change_pct": 0.0,
        "asof": datetime(2026, 4, 28, tzinfo=timezone.utc),
    }


def _make_data_layer() -> DataLayer:
    """DataLayer with K=2 data citations."""
    return DataLayer(
        technical=TechMomentum(
            rsi_14=58.0, mfi_14=None, atr_pct=2.0, cmf_20=None, obv_ratio=None,
            ma_stack="정배열", rvol_20=1.4, box_position=None,
            summary_line="RSI 58", citations=[1],
        ),
        macro=MacroContext(
            one_line="USD/KRW 1378", vix=18.7, fx_pairs={"USD/KRW": 1378.0},
            us_10y=4.6, sensitivities=[], upcoming_events=[],
            citations=[2],
        ),
        fundamentals=Fundamentals(per=14.2, pbr=1.4, citations=[]),
        news=[],
        relations_data=[
            Relation(
                target_ticker="000660",
                target_name="SK하이닉스",
                relation_type="peer",
                strength=0.9,
                today_change_pct=2.8,
                notes=None,
                citation_ids=[],
            )
        ],
        data_citations=[
            Citation(id=1, source_type="db", label="DB · price_history"),
            Citation(id=2, source_type="market_data", label="DB · macro_factors"),
        ],
    )


def _make_analyst_output() -> AnalystOutput:
    """AnalystOutput with M=1 analyst citation referencing it from glance/thesis/decision."""
    return AnalystOutput(
        glance=GlanceVerdict(
            final_grade="B", stance="WATCH", entry_stage="WAIT",
            one_line="HBM 모멘텀 + 외국인 매도 부담",
            citations=[1],  # references analyst pool id=1
        ),
        thesis=Thesis(
            core_thesis="HBM 사이클 유지",
            supports=[
                Claim(text="a", citations=[1]),
                Claim(text="b", citations=[1]),
                Claim(text="c", citations=[]),
            ],
            opposes=[
                Claim(text="x", citations=[1]),
                Claim(text="y", citations=[]),
            ],
            catalysts=[],
            no_catalysts_reason="14일 윈도 일정 없음",
            scenarios=[
                Scenario(name="BULL", probability=0.25, scenario_price=110, scenario_change_pct=10, rationale="x"),
                Scenario(name="BASE", probability=0.55, scenario_price=100, scenario_change_pct=0, rationale="x"),
                Scenario(name="BEAR", probability=0.20, scenario_price=90, scenario_change_pct=-10, rationale="x"),
            ],
            citations=[1],
        ),
        relations_narrative=RelationsNarrative(
            one_line="SK하이닉스 +2.8% 동조",
            notes_by_target={"000660": "HBM 동조 수혜"},
            citations=[],
        ),
        decision=Decision(
            stance="WATCH", sizing_note="대기",
            support_price=95, risk_threshold=85, citations=[1],
        ),
        interp_citations=[
            Citation(id=1, source_type="web", label="분석가 도입 출처"),
        ],
    )


# ---------------------------------------------------------------------------
# compose() — pure function, no DB
# ---------------------------------------------------------------------------


def test_compose_merges_data_and_analyst_into_stock_card():
    data = _make_data_layer()
    analyst = _make_analyst_output()
    card = compose("ENG1", data, analyst, _identity("ENG1"))
    assert isinstance(card, StockCard)
    assert card.ticker == "ENG1"
    assert card.glance.final_grade == "B"
    assert card.thesis.core_thesis == "HBM 사이클 유지"
    assert card.technical.rsi_14 == 58.0
    assert card.macro.us_10y == 4.6
    assert card.fundamentals.per == 14.2
    assert card.schema_version == "v2"
    assert card.persona_version == "analyst_v1"


def test_compose_renumbers_citations_globally():
    """Analyst pool ids 1..M get offset by K (data pool size). Per spec, the
    LLM only references its own interp pool; data pool ids 1..K are invisible
    to the LLM, so numeric overlap is semantically not ambiguous — compose
    always treats LLM-side citations as interp references and shifts by +K.
    """
    data = _make_data_layer()  # K = 2
    analyst = _make_analyst_output()  # M = 1, analyst citation id=1
    card = compose("ENG1", data, analyst, _identity())

    # Final pool size = K + M = 3
    assert len(card.citations) == 3
    final_ids = [c.id for c in card.citations]
    assert final_ids == [1, 2, 3]

    # Data citations unchanged: technical references id=1 (data only), macro id=2.
    assert card.technical.citations == [1]
    assert card.macro.citations == [2]

    # Analyst references shifted by K=2: glance.citations [1] → [3]
    assert card.glance.citations == [3]
    assert card.thesis.citations == [3]
    assert card.thesis.supports[0].citations == [3]
    assert card.decision.citations == [3]


def test_compose_merges_relations_data_with_narrative():
    """Relation.notes filled from analyst.relations_narrative.notes_by_target."""
    data = _make_data_layer()
    analyst = _make_analyst_output()
    card = compose("ENG1", data, analyst, _identity())
    assert card.relations.one_line == "SK하이닉스 +2.8% 동조"
    assert len(card.relations.relations) == 1
    rel = card.relations.relations[0]
    assert rel.target_ticker == "000660"
    assert rel.notes == "HBM 동조 수혜"  # overlaid from narrative


def test_compose_server_fields_win_over_llm():
    """Identity is injected last — analyst can't override ticker/name/price."""
    data = _make_data_layer()
    analyst = _make_analyst_output()
    identity = _identity("REAL")
    identity["price"] = 12345.0
    card = compose("REAL", data, analyst, identity)
    assert card.ticker == "REAL"
    assert card.price == 12345.0
    assert card.name_ko == "엔진테스트"


def test_compose_drops_truly_dangling_citation_ref():
    """LLM cites an id that is neither in interp pool nor in data pool 1..K —
    compose drops it silently (logged at INFO), card still renders.

    Previously raised ValueError; spec change after demo observed LLM
    hallucinating dangling ids while leaving interp_citations empty.
    """
    data = _make_data_layer()
    analyst = _make_analyst_output()
    # Mutate: glance refs id=99, interp has only id=1, data pool has 2 ids
    # → 99 is past both pools → dropped.
    analyst.glance.citations = [99]
    card = compose("ENG1", data, analyst, _identity())
    assert card.glance.citations == []


def test_compose_drops_unregistered_llm_citation():
    """LLM cites id=2 without registering it in interp_citations. Per spec
    the LLM may only cite from its own pool, so unregistered ids are treated
    as hallucinations and dropped — even if the same number happens to exist
    as a data pool id (the LLM can't see the data pool).
    """
    data = _make_data_layer()
    analyst = _make_analyst_output()  # interp pool only has id=1
    k = len(data.data_citations)
    assert k >= 2, "fixture needs ≥ 2 data citations"
    assert 2 not in {c.id for c in analyst.interp_citations}
    analyst.glance.citations = [2]
    card = compose("ENG1", data, analyst, _identity())
    assert card.glance.citations == [], "unregistered id must be dropped"


def test_compose_shifts_interp_citations_even_when_overlapping_data_range():
    """When interp pool id=1 is also numerically inside the data range 1..K,
    compose still shifts by +K — there's no semantic ambiguity because the
    LLM contract is to only cite from interp. Production log showed K=127
    + interp={1..4} dropping every LLM footnote under the old strict-ambiguity
    rule; this regression test pins down the lenient behavior.
    """
    data = _make_data_layer()  # K=2, so id=1 is also a valid data id
    analyst = _make_analyst_output()  # has interp_citations[id=1]
    k = len(data.data_citations)
    assert k >= 1
    assert 1 in {c.id for c in analyst.interp_citations}
    analyst.glance.citations = [1]
    card = compose("ENG1", data, analyst, _identity())
    assert card.glance.citations == [k + 1], "interp id must shift by +K"


def test_compose_stubs_missing_data_sections():
    """When DataLayer.technical is None, compose injects a placeholder."""
    data = _make_data_layer()
    data.technical = None
    data.macro = None
    data.fundamentals = None
    analyst = _make_analyst_output()
    card = compose("ENG1", data, analyst, _identity())
    assert card.technical.rsi_14 is None
    assert "데이터" in card.technical.summary_line
    assert card.macro.vix is None
    assert card.fundamentals.per is None


def test_compose_handles_empty_relations():
    data = _make_data_layer()
    data.relations_data = []
    analyst = _make_analyst_output()
    card = compose("ENG1", data, analyst, _identity())
    assert card.relations.relations == []
    assert card.relations.one_line == "SK하이닉스 +2.8% 동조"  # narrative still


# ---------------------------------------------------------------------------
# analyze() — with DB, mocked stages
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_for_engine(db, monkeypatch):
    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("app.services.analyst.engine.async_session", _session)
    monkeypatch.setattr("app.services.analyst.data_layer.async_session", _session)
    return db


@pytest_asyncio.fixture(autouse=True)
async def clear_locks():
    """Tests must not share locks across cases."""
    _TICKER_LOCKS.clear()
    yield
    _TICKER_LOCKS.clear()


@pytest.mark.asyncio
async def test_analyze_persists_card_to_analyses_table(db_for_engine, monkeypatch):
    db = db_for_engine
    s = Stock(ticker="ENG1", name="엔진테스트", market="KRX", sector="기타", current_price=100.0)
    db.add(s)
    await db.flush()
    _seed_price_history(db, s.id)
    await db.commit()

    monkeypatch.setattr(
        "app.services.analyst.engine.run_research",
        AsyncMock(return_value={"findings": [], "citations": []}),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.assemble_data_layer",
        AsyncMock(return_value=_make_data_layer()),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.run_synthesize",
        AsyncMock(return_value=_make_analyst_output()),
    )

    out = await analyze("ENG1")
    assert out.ticker == "ENG1"
    assert out.schema_version == "v2"

    rows = (
        await db.execute(select(Analysis).where(Analysis.stock_id == s.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].schema_version == "v2"
    assert rows[0].persona_version == "analyst_v1"
    assert rows[0].card_data["ticker"] == "ENG1"


@pytest.mark.asyncio
async def test_analyze_preserves_phase_a_keywords(db_for_engine, monkeypatch):
    """REGRESSION CRITICAL — Phase A KeywordDetail rows must survive v2 upsert.

    DB unique constraint forces one Analysis row per (stock, date, period_type),
    so v1 and v2 share a row by column. v2 bumps schema_version + writes
    card_data; the Phase A keyword children must not be deleted.
    """
    db = db_for_engine
    s = Stock(ticker="ENG2", name="x", market="KRX", sector="x", current_price=100.0)
    db.add(s)
    await db.flush()
    _seed_price_history(db, s.id)
    a = Analysis(
        stock_id=s.id,
        date=_date.today(),
        period_type="daily",
        summary="phase-a-summary",
        feedback="phase-a-feedback",
        schema_version="v1",
    )
    db.add(a)
    await db.flush()
    db.add(
        KeywordDetail(
            analysis_id=a.id,
            keyword="HBM",
            type="positive",
            detail="HBM3E 양산",
            source="news",
            impact_level="high",
            duration="medium",
        )
    )
    await db.commit()

    monkeypatch.setattr(
        "app.services.analyst.engine.run_research",
        AsyncMock(return_value={"findings": []}),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.assemble_data_layer",
        AsyncMock(return_value=_make_data_layer()),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.run_synthesize",
        AsyncMock(return_value=_make_analyst_output()),
    )

    await analyze("ENG2")

    rows = (
        await db.execute(select(Analysis).where(Analysis.stock_id == s.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].schema_version == "v2"
    assert rows[0].card_data["ticker"] == "ENG2"

    kws = (
        await db.execute(
            select(KeywordDetail).where(KeywordDetail.analysis_id == a.id)
        )
    ).scalars().all()
    assert len(kws) == 1
    assert kws[0].keyword == "HBM"


@pytest.mark.asyncio
async def test_analyze_upserts_when_same_day_v2_exists(db_for_engine, monkeypatch):
    db = db_for_engine
    s = Stock(ticker="ENG3", name="x", market="KRX", sector="x", current_price=100.0)
    db.add(s)
    await db.flush()
    _seed_price_history(db, s.id)
    db.add(
        Analysis(
            stock_id=s.id,
            date=_date.today(),
            period_type="daily",
            summary="old",
            feedback="old",
            schema_version="v2",
            card_data={"ticker": "ENG3", "stale": True},
        )
    )
    await db.commit()

    monkeypatch.setattr(
        "app.services.analyst.engine.run_research",
        AsyncMock(return_value={"findings": []}),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.assemble_data_layer",
        AsyncMock(return_value=_make_data_layer()),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.run_synthesize",
        AsyncMock(return_value=_make_analyst_output()),
    )

    await analyze("ENG3")
    rows = (
        await db.execute(select(Analysis).where(Analysis.stock_id == s.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].schema_version == "v2"
    assert rows[0].card_data.get("stale") is None  # upserted, not appended


@pytest.mark.asyncio
async def test_analyze_fails_fast_when_price_zero(db_for_engine):
    db = db_for_engine
    s = Stock(ticker="ZERO", name="x", market="KRX", sector="x", current_price=0)
    db.add(s)
    await db.commit()
    with pytest.raises(ValueError, match="not analyzable"):
        await analyze("ZERO")


@pytest.mark.asyncio
async def test_get_ticker_lock_returns_per_ticker_singleton():
    a1 = await _get_ticker_lock("AAA")
    a2 = await _get_ticker_lock("AAA")
    b = await _get_ticker_lock("BBB")
    assert a1 is a2
    assert a1 is not b


@pytest.mark.asyncio
async def test_analyze_serializes_concurrent_calls_for_same_ticker(monkeypatch):
    """Two analyze() calls for the same ticker must serialize on the lock.

    All DB/LLM-touching steps are mocked so the test only exercises the lock
    mechanism — no session contention from the shared test fixture.
    """
    call_log: list[str] = []

    async def track_research(ticker):
        call_log.append(f"start:{ticker}")
        await asyncio.sleep(0.05)
        call_log.append(f"end:{ticker}")
        return {"findings": []}

    monkeypatch.setattr(
        "app.services.analyst.engine.is_analyzable",
        AsyncMock(return_value=(True, None)),
    )
    monkeypatch.setattr("app.services.analyst.engine.run_research", track_research)
    monkeypatch.setattr(
        "app.services.analyst.engine.assemble_data_layer",
        AsyncMock(return_value=_make_data_layer()),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.run_synthesize",
        AsyncMock(return_value=_make_analyst_output()),
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.fetch_stock_identity",
        AsyncMock(return_value=_identity("LOCK")),
    )
    monkeypatch.setattr("app.services.analyst.engine._persist", AsyncMock())

    await asyncio.gather(analyze("LOCK"), analyze("LOCK"))
    assert call_log == ["start:LOCK", "end:LOCK", "start:LOCK", "end:LOCK"]
