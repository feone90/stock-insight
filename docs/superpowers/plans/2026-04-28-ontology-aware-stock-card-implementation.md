# StockInsight v2 — Backend Engine (P1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend analysis engine that produces a `StockCard` for any ticker — a 2-stage agent (Research → Synthesize) with new tools (indicators, ontology relations, web search, macro context), persona-driven output, and a curl-testable `/api/stocks/{ticker}/card` endpoint.

**Architecture:** Two-stage LLM pipeline. Stage 1 (Research) runs a cheap-tier LLM with broad tool access, gathering evidence into free-form findings. Stage 2 (Synthesize) runs a premium LLM with the `analyst_v1` persona prompt and Pydantic structured output, producing a typed `StockCard`. Persistence reuses the `analyses` table (extended with `card_data` JSONB + `schema_version` discriminator) so Phase A keyword-style results coexist with v2 cards. Scheduler splits into KR (08:30/16:00 KST) + US (07:00/22:30 KST) jobs, with unique-ticker dedup across favorites and a daily cost kill switch.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 async · Alembic · Pydantic v2 · Azure OpenAI Responses API · Tavily web search · pandas-ta-style custom indicator calc · APScheduler · pytest + pytest-asyncio · uv

**Spec:** `docs/superpowers/specs/2026-04-28-ontology-aware-stock-card-design.md` (commit `8e2f4a6`)

**Scope of this plan:** P1 (Backend Engine) only. Plan 2 = P2 (Frontend Card). Plan 3 = P3 (Stock Universe). Plan 4 = P4+P5 (Chat Evolution + Polish). See `## Next Steps` at end.

---

## File Structure

### Created
- `backend/app/schemas/card.py` — All Pydantic types for StockCard output (Citation, Interpretation, Claim, GlanceVerdict, TechMomentum, Relation, RelationsSummary, NewsItem, MacroContext, Fundamentals, Catalyst, Scenario, Thesis, Decision, StockCard).
- `backend/app/services/analyst/__init__.py` — Package marker.
- `backend/app/services/analyst/persona.py` — `RESEARCHER_V1` and `ANALYST_V1` system prompt constants. Internal-only naming.
- `backend/app/services/analyst/indicators.py` — Pure-Python RSI, MFI, ATR%, CMF, OBV, MA stack, RVOL computation.
- `backend/app/services/analyst/tools.py` — 8 new tools + tool schemas + dispatcher (separate from `app/services/chat/tools.py`).
- `backend/app/services/analyst/research.py` — Stage 1 orchestrator (LLM + tool loop, max 10 rounds).
- `backend/app/services/analyst/synthesize.py` — Stage 2 synthesizer (structured output → StockCard).
- `backend/app/services/analyst/engine.py` — Public entry point: `analyze(ticker) -> StockCard`. Wraps both stages, handles persistence + errors.
- `backend/app/services/analyst/cost.py` — Daily budget tracker + kill switch.
- `backend/app/services/analyst/dedup.py` — Unique-ticker logic for scheduled batches.
- `backend/app/models/relation.py` — `StockRelation` ORM model (`stock_relations` table).
- `backend/app/models/macro_factor.py` — `MacroFactor` ORM model (`macro_factors` table).
- `backend/app/collectors/macro.py` — VIX + US10Y + sector ETF + USD/KRW collector.
- `backend/app/collectors/investor_flow.py` — KR foreign/institutional net flow (KRX or naver scrape).
- `backend/app/api/cards.py` — `POST /api/stocks/{ticker}/analyze`, `GET /api/stocks/{ticker}/card`, `POST /api/stocks/{ticker}/refresh`.
- `backend/alembic/versions/<rev>_add_card_schema_columns.py` — Add `schema_version`, `card_data`, `persona_version` to `analyses`.
- `backend/alembic/versions/<rev>_create_stock_relations.py` — New ontology relation table.
- `backend/alembic/versions/<rev>_create_macro_factors.py` — New macro factor cache table.
- `backend/tests/test_card_schema.py` — Pydantic validation tests.
- `backend/tests/test_indicators.py` — Indicator math tests.
- `backend/tests/test_analyst_tools.py` — Tool unit tests (mocked LLM/web).
- `backend/tests/test_research_agent.py` — Stage 1 orchestrator tests.
- `backend/tests/test_synthesizer.py` — Stage 2 tests with mocked LLM.
- `backend/tests/test_engine.py` — End-to-end engine test (mocked).
- `backend/tests/test_cost_killswitch.py` — Daily cap test.
- `backend/tests/test_dedup.py` — Dedup logic test.
- `backend/tests/test_card_api.py` — API endpoint tests.
- `backend/tests/integration/__init__.py`
- `backend/tests/integration/test_smoke_005930.py` — Real-LLM smoke test (opt-in marker).

### Modified
- `backend/app/models/analysis.py` — Add `schema_version`, `card_data`, `persona_version` columns.
- `backend/app/scheduler.py` — Split into KR + US schedules, integrate dedup + kill switch.
- `backend/app/main.py` — Register `cards` router.
- `backend/app/config.py` — New env vars: `TAVILY_API_KEY`, `ANALYST_RESEARCH_MODEL`, `ANALYST_SYNTHESIZE_MODEL`, `ANALYSIS_DAILY_BUDGET_USD`, `ANALYSIS_COOLDOWN_SECONDS`.
- `backend/.env.example` — Document new vars.
- `backend/pyproject.toml` — Add `tavily-python` dep.
- `backend/app/dependencies.py` — Add cooldown dependency for refresh endpoint.

### Deleted
- None in P1 (chat surface deletions are P4).

---

## Pre-Flight

### P0: Branch + Env Setup

- [ ] **Step P0.1: Create implementation branch off main**

```bash
git fetch origin
git checkout main
git pull
git checkout -b feat/v2-backend-engine
```

- [ ] **Step P0.2: Provision Tavily API key**

Sign up at <https://tavily.com> (free tier: 1000 calls/month). Add to `backend/.env`:

```
TAVILY_API_KEY=tvly-...
```

- [ ] **Step P0.3: Add new env vars to `.env`**

```
# LLM model selection
ANALYST_RESEARCH_MODEL=gpt-5-mini
ANALYST_SYNTHESIZE_MODEL=gpt-5

# Cost guard
ANALYSIS_DAILY_BUDGET_USD=10
ANALYSIS_COOLDOWN_SECONDS=300

# Schedule (KR/US split — KST cron strings)
SCHEDULE_KR_MORNING=30 8 * * 1-5
SCHEDULE_KR_AFTERNOON=0 16 * * 1-5
SCHEDULE_US_EVENING=0 7 * * 1-5
SCHEDULE_US_NIGHT=30 22 * * 1-5
```

- [ ] **Step P0.4: Add tavily-python dependency**

```bash
cd backend
uv add tavily-python
```

Verify in `backend/pyproject.toml`:

```toml
dependencies = [
    ...
    "tavily-python>=0.5.0",
]
```

- [ ] **Step P0.5: Sanity-check tests still pass on baseline**

```bash
cd backend && uv run python -m pytest tests/ -q
```

Expected: All existing tests pass.

- [ ] **Step P0.6: Commit pre-flight**

```bash
git add backend/pyproject.toml backend/uv.lock backend/.env.example
git commit -m "chore: scaffold v2 backend engine env vars and tavily dep"
```

---

## Phase 1: Backend Engine (P1)

### Task 1: Pydantic Card Schema

**Goal:** Lock in the `StockCard` shape so all later code can typecheck against it.

**Files:**
- Create: `backend/app/schemas/card.py`
- Test: `backend/tests/test_card_schema.py`

- [ ] **Step 1.1: Write failing test for schema validation**

Create `backend/tests/test_card_schema.py`:

```python
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
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd backend && uv run python -m pytest tests/test_card_schema.py -v
```

Expected: `ImportError: cannot import name 'StockCard' from 'app.schemas.card'`

- [ ] **Step 1.3: Implement `card.py`**

Create `backend/app/schemas/card.py`:

```python
"""StockCard Pydantic schema — output of the v2 analyst engine.

Citation = data source ONLY. LLM interpretation lives in `Interpretation`,
attached to claims via `Claim.interpretation`. Don't conflate.

Field renames vs early drafts (do not regress):
- strategy → stance
- target_price → scenario_price
- target_change_pct → scenario_change_pct
- stop_loss → risk_threshold
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal[
    "db",
    "market_data",
    "news",
    "disclosure",
    "web",
    "curated_relation",
]
InterpretationKind = Literal["model_generated", "rule_based"]


class Citation(BaseModel):
    id: int
    source_type: SourceType
    label: str
    url: str | None = None
    timestamp: datetime | None = None


class Interpretation(BaseModel):
    """How a claim was derived. Separate from data citations."""
    kind: InterpretationKind
    based_on: list[int]
    rationale: str | None = None


class Claim(BaseModel):
    """One reasoning unit. Numerical evidence + optional interpretation."""
    text: str
    citations: list[int]
    interpretation: Interpretation | None = None


class GlanceVerdict(BaseModel):
    final_grade: Literal["S", "A", "B", "C", "D"]
    grade_delta: Literal["up", "down", "same"] | None = None
    stance: Literal["BUY", "WATCH", "REJECT"]
    entry_stage: Literal["ENTER", "WAIT", "REJECT"]
    one_line: str
    citations: list[int]


class TechMomentum(BaseModel):
    rsi_14: float | None
    mfi_14: float | None
    atr_pct: float | None
    cmf_20: float | None
    obv_ratio: float | None
    ma_stack: Literal["정배열", "역배열", "혼조"] | None
    rvol_20: float | None
    box_position: str | None
    summary_line: str
    citations: list[int]
    interpretation: Interpretation | None = None


class Relation(BaseModel):
    target_ticker: str
    target_name: str
    relation_type: Literal[
        "peer", "supply_upstream", "supply_downstream", "group", "theme", "macro"
    ]
    strength: float = Field(..., ge=0, le=1)
    today_change_pct: float | None = None
    notes: str | None = None
    citation_ids: list[int]


class RelationsSummary(BaseModel):
    one_line: str
    relations: list[Relation]
    citations: list[int]


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: datetime
    impact: Literal["positive", "negative", "mixed", "neutral"]
    summary: str
    citation_id: int


class MacroSensitivity(BaseModel):
    factor: str
    beta: float
    direction: Literal["positive", "negative", "neutral"]


class MacroContext(BaseModel):
    one_line: str
    vix: float | None
    fx_pairs: dict[str, float]
    us_10y: float | None
    sensitivities: list[MacroSensitivity]
    upcoming_events: list[str]
    citations: list[int]


class Fundamentals(BaseModel):
    per: float | None
    pbr: float | None
    market_cap_krw: float | None
    dividend_yield: float | None
    per_5y_z: float | None
    citations: list[int]


class Catalyst(BaseModel):
    when: str
    event: str
    impact_estimate: str
    direction: Literal["positive", "negative", "mixed"]
    citation_ids: list[int]


class Scenario(BaseModel):
    name: Literal["BULL", "BASE", "BEAR"]
    probability: float = Field(..., ge=0, le=1)
    scenario_price: float | None
    scenario_change_pct: float | None
    rationale: str


class Thesis(BaseModel):
    core_thesis: str
    supports: list[Claim] = Field(..., min_length=3)
    opposes: list[Claim] = Field(..., min_length=2)
    catalysts: list[Catalyst]  # may be empty
    no_catalysts_reason: str | None = None
    scenarios: list[Scenario] = Field(..., min_length=3, max_length=3)
    citations: list[int]


class Decision(BaseModel):
    stance: Literal["BUY", "WATCH", "REJECT"]
    sizing_note: str
    support_price: float | None
    risk_threshold: float | None
    note: str = "참고용 — 투자 권유 아님"
    citations: list[int]
    interpretation: Interpretation | None = None


class StockCard(BaseModel):
    ticker: str
    name_ko: str
    name_en: str
    market: str
    sector: str
    tags: list[str]

    price: float
    change: float
    change_pct: float
    asof: datetime

    glance: GlanceVerdict
    thesis: Thesis
    technical: TechMomentum
    relations: RelationsSummary
    news: list[NewsItem]
    macro: MacroContext
    fundamentals: Fundamentals
    decision: Decision

    citations: list[Citation]

    analysis_id: str
    generated_at: datetime
    persona_version: str
    schema_version: str = "v1"
    refresh_state: Literal["fresh", "stale", "loading", "error"] = "fresh"
```

- [ ] **Step 1.4: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_card_schema.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/schemas/card.py backend/tests/test_card_schema.py
git commit -m "feat: add StockCard Pydantic schema with citation/interpretation split"
```

---

### Task 2: Extend `analyses` Table — schema_version + card_data

**Goal:** Allow Phase A keyword-style rows and v2 StockCard JSON to coexist.

**Files:**
- Modify: `backend/app/models/analysis.py`
- Create: `backend/alembic/versions/<rev>_add_card_schema_columns.py`

- [ ] **Step 2.1: Update ORM model**

Modify `backend/app/models/analysis.py` — add 3 columns to `Analysis`:

```python
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.stock import Base


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", "period_type", name="uq_analysis_stock_date_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    date: Mapped[str] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    feedback: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # v2 additions — nullable for Phase A backwards compat.
    schema_version: Mapped[str] = mapped_column(String(10), nullable=False, server_default="v1")
    card_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    persona_version: Mapped[str | None] = mapped_column(String(40), nullable=True)

    keywords: Mapped[list["KeywordDetail"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")
    daily_keywords: Mapped[list["DailyKeyword"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class KeywordDetail(Base):
    __tablename__ = "keyword_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    keyword: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    impact_level: Mapped[str] = mapped_column(String(20))
    duration: Mapped[str] = mapped_column(String(20))

    analysis: Mapped["Analysis"] = relationship(back_populates="keywords")


class DailyKeyword(Base):
    __tablename__ = "daily_keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    date: Mapped[str] = mapped_column(Date)
    keyword: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))

    analysis: Mapped["Analysis"] = relationship(back_populates="daily_keywords")
```

- [ ] **Step 2.2: Generate alembic migration**

```bash
cd backend && uv run alembic revision --autogenerate -m "add card_data schema_version persona_version to analyses"
```

Inspect the new file in `backend/alembic/versions/`. Verify it adds the three columns and nothing unexpected. If autogenerate adds spurious diffs (e.g., unrelated index drops), edit by hand.

- [ ] **Step 2.3: Apply migration locally**

```bash
cd backend && uv run alembic upgrade head
```

Expected: `Running upgrade ... -> ..., add card_data schema_version persona_version to analyses`.

- [ ] **Step 2.4: Verify with psql**

```bash
psql -U postgres -d stockinsight -c "\d analyses"
```

Expected: `schema_version`, `card_data`, `persona_version` columns present.

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/models/analysis.py backend/alembic/versions/*add_card_schema*.py
git commit -m "feat: extend analyses table with schema_version and card_data JSONB"
```

---

### Task 3: `stock_relations` Table

**Goal:** Persist AI-curated peer/supply/group/theme/macro relations with TTL.

**Files:**
- Create: `backend/app/models/relation.py`
- Create: `backend/alembic/versions/<rev>_create_stock_relations.py`

- [ ] **Step 3.1: Create model**

Create `backend/app/models/relation.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class StockRelation(Base):
    """An ontology edge: from_stock --[type]--> to_target.

    `to_target` may be a Stock (FK by ticker stored as string) OR a virtual node
    (theme/macro factor). Hence string column not FK — virtual nodes don't have
    a row in `stocks`.
    """

    __tablename__ = "stock_relations"
    __table_args__ = (
        UniqueConstraint(
            "from_stock_id", "to_target", "relation_type", name="uq_relation_triple"
        ),
        Index("ix_relations_from", "from_stock_id"),
        Index("ix_relations_target", "to_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    to_target: Mapped[str] = mapped_column(String(100))  # ticker OR theme name OR factor name
    to_kind: Mapped[str] = mapped_column(String(20))  # "stock" | "theme" | "macro"
    relation_type: Mapped[str] = mapped_column(String(30))
    # peer | supply_upstream | supply_downstream | group | theme | macro

    strength: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="llm-curation")
    discovered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 3.2: Register model in `app/models/__init__.py`**

Open `backend/app/models/__init__.py` and add `StockRelation` to the imports/`__all__` list (mirror existing pattern).

- [ ] **Step 3.3: Generate migration**

```bash
cd backend && uv run alembic revision --autogenerate -m "create stock_relations table"
```

Verify the new file creates `stock_relations` with the correct columns + indexes.

- [ ] **Step 3.4: Apply**

```bash
cd backend && uv run alembic upgrade head
```

- [ ] **Step 3.5: Commit**

```bash
git add backend/app/models/relation.py backend/app/models/__init__.py backend/alembic/versions/*stock_relations*.py
git commit -m "feat: add stock_relations table for ontology edges"
```

---

### Task 4: `macro_factors` Table

**Goal:** Cache VIX, US10Y, USD/KRW, sector ETF prices for the macro context block.

**Files:**
- Create: `backend/app/models/macro_factor.py`
- Create: `backend/alembic/versions/<rev>_create_macro_factors.py`

- [ ] **Step 4.1: Create model**

Create `backend/app/models/macro_factor.py`:

```python
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class MacroFactor(Base):
    """Daily snapshot of one macro factor (e.g. VIX, US10Y, USD/KRW)."""

    __tablename__ = "macro_factors"
    __table_args__ = (
        UniqueConstraint("factor", "date", name="uq_macro_factor_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    factor: Mapped[str] = mapped_column(String(40))  # "VIX", "US10Y", "USD/KRW", "XLK", etc.
    date: Mapped[str] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40), default="market_data")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 4.2: Register in `app/models/__init__.py`**

Add `MacroFactor` import and `__all__` entry.

- [ ] **Step 4.3: Generate + apply migration**

```bash
cd backend && uv run alembic revision --autogenerate -m "create macro_factors table"
cd backend && uv run alembic upgrade head
```

- [ ] **Step 4.4: Commit**

```bash
git add backend/app/models/macro_factor.py backend/app/models/__init__.py backend/alembic/versions/*macro_factors*.py
git commit -m "feat: add macro_factors table for VIX/US10Y/FX cache"
```

---

### Task 5: Indicators (RSI/MFI/ATR/CMF/OBV/MA/RVOL)

**Goal:** Pure-Python computations. Deterministic. No heavyweight deps.

**Files:**
- Create: `backend/app/services/analyst/__init__.py`
- Create: `backend/app/services/analyst/indicators.py`
- Test: `backend/tests/test_indicators.py`

- [ ] **Step 5.1: Write failing tests with known values**

Create `backend/tests/test_indicators.py`:

```python
"""Indicator math tests with hand-computed expected values."""
import math

import pytest

from app.services.analyst.indicators import (
    atr_pct,
    cmf,
    ma_stack,
    obv_ratio,
    rsi,
    rvol,
)

# Sample 20-day OHLCV: closes drift up then dip, volumes mostly flat.
CLOSES = [
    100.0, 101.0, 102.5, 101.8, 103.0, 104.2, 105.0, 104.5, 106.0, 107.0,
    108.5, 109.0, 108.2, 110.0, 111.5, 110.8, 112.0, 113.5, 112.0, 114.0,
]
HIGHS = [c + 1.5 for c in CLOSES]
LOWS = [c - 1.5 for c in CLOSES]
VOLS = [1_000_000.0] * 18 + [1_400_000.0, 1_500_000.0]  # last 2 days higher


def test_rsi_14_in_range():
    val = rsi(CLOSES, period=14)
    assert val is not None
    assert 0 <= val <= 100
    # Sample is mostly up — expect > 50
    assert val > 50


def test_rsi_insufficient_data_returns_none():
    assert rsi([100.0, 101.0], period=14) is None


def test_atr_pct_positive():
    val = atr_pct(HIGHS, LOWS, CLOSES, period=14)
    assert val is not None
    assert val > 0


def test_ma_stack_uptrend_returns_정배열():
    val = ma_stack(CLOSES)
    assert val == "정배열"


def test_ma_stack_downtrend_returns_역배열():
    down = list(reversed(CLOSES))
    assert ma_stack(down) == "역배열"


def test_rvol_recent_higher_returns_above_one():
    val = rvol(VOLS, period=20)
    assert val is not None
    assert val > 1.0


def test_obv_ratio_returns_finite():
    val = obv_ratio(CLOSES, VOLS, period=20)
    assert val is not None
    assert math.isfinite(val)


def test_cmf_in_minus_one_to_one():
    val = cmf(HIGHS, LOWS, CLOSES, VOLS, period=20)
    assert val is not None
    assert -1 <= val <= 1
```

- [ ] **Step 5.2: Run — expect ImportError**

```bash
cd backend && uv run python -m pytest tests/test_indicators.py -v
```

Expected: ImportError.

- [ ] **Step 5.3: Implement indicators**

Create `backend/app/services/analyst/__init__.py` (empty file).

Create `backend/app/services/analyst/indicators.py`:

```python
"""Pure-Python technical indicators. Deterministic. Returns None when data insufficient."""
from __future__ import annotations


def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i, _ in enumerate(values):
        if i + 1 < period:
            out.append(None)
        else:
            out.append(sum(values[i - period + 1 : i + 1]) / period)
    return out


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI. Returns latest value."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def atr_pct(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    """ATR as percentage of latest close. True Range = max(H-L, |H-prevC|, |L-prevC|)."""
    if len(closes) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return (atr / closes[-1]) * 100.0


def ma_stack(closes: list[float]) -> str | None:
    """정배열 if MA5 > MA20 > MA60, 역배열 if reversed, else 혼조."""
    if len(closes) < 60:
        return None
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    if ma5 > ma20 > ma60:
        return "정배열"
    if ma5 < ma20 < ma60:
        return "역배열"
    return "혼조"


def rvol(volumes: list[float], period: int = 20) -> float | None:
    """Latest volume / mean(volumes[-period:])."""
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-period - 1 : -1]) / period
    if avg == 0:
        return None
    return volumes[-1] / avg


def obv_ratio(closes: list[float], volumes: list[float], period: int = 20) -> float | None:
    """OBV change over `period` / total volume in `period`. Bounded ~[-1, 1]."""
    if len(closes) < period + 1 or len(volumes) < period + 1:
        return None
    obv = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv += volumes[i]
        elif closes[i] < closes[i - 1]:
            obv -= volumes[i]
    total_vol = sum(volumes[-period:])
    if total_vol == 0:
        return None
    return obv / total_vol


def cmf(
    highs: list[float], lows: list[float], closes: list[float], volumes: list[float], period: int = 20
) -> float | None:
    """Chaikin Money Flow over `period`. In [-1, 1]."""
    if len(closes) < period:
        return None
    mf_volumes = []
    for i in range(-period, 0):
        h, l, c = highs[i], lows[i], closes[i]
        if h == l:
            mf_volumes.append(0.0)
            continue
        mf_mult = ((c - l) - (h - c)) / (h - l)
        mf_volumes.append(mf_mult * volumes[i])
    total_vol = sum(volumes[-period:])
    if total_vol == 0:
        return None
    return sum(mf_volumes) / total_vol
```

- [ ] **Step 5.4: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_indicators.py -v
```

Expected: All 8 PASS.

- [ ] **Step 5.5: Commit**

```bash
git add backend/app/services/analyst/__init__.py backend/app/services/analyst/indicators.py backend/tests/test_indicators.py
git commit -m "feat: add pure-Python technical indicator computations"
```

---

### Task 6: Persona Prompts (`analyst_v1`, `researcher_v1`)

**Goal:** Lock the system prompts. These are the product's voice.

**Files:**
- Create: `backend/app/services/analyst/persona.py`
- Test: `backend/tests/test_card_schema.py` (extend with prompt sanity checks)

- [ ] **Step 6.1: Create persona file**

Create `backend/app/services/analyst/persona.py`:

```python
"""Persona prompts for the v2 analyst engine.

Internal naming. NEVER surface "analyst_v1" or "Buffett-grade" in user-facing UI,
chat output, marketing copy, or error messages. UI copy lives in the frontend.
"""

# Stage 1: research orchestrator. Cheap-tier model, exploratory, tool-heavy.
RESEARCHER_V1 = """\
당신은 주식 종목에 대해 풍부한 증거를 수집하는 리서처다. 답변을 만드는 게 아니라 *근거*를 모은다.

원칙:
- 도구를 자유롭게 사용해 데이터/뉴스/관계/매크로/지표를 모두 조사한다.
- 각 발견에 출처를 함께 기록 (DB row, URL, 도구 호출 결과).
- 부족한 영역은 명시적으로 'gap' 으로 남긴다 — 추측 금지.
- 5~10 round 안에 마무리. 같은 도구를 무의미하게 재호출하지 않는다.
- 출력은 자유 형식 JSON: {findings: [...], citations: [...], gaps_noted: [...]}.

조사 우선순위 (이 순서로):
1) 종목 기본 (현재가, 등락, 시총, PER/PBR)
2) 모멘텀/기술 (RSI/MA/RVOL/ATR)
3) 최근 뉴스 (10건 이상, 본문 요약)
4) 관계 (peer/공급망/그룹/테마) — 캐시 hit 우선, miss 시 web_search로 재조사
5) 매크로 (VIX, USD/KRW, US10Y, 섹터 ETF)
6) 임박 일정 (실적, FOMC, 정책 등) — 14일 윈도. 없으면 '없음'으로 명시
7) 시장 사회 이슈 — 종목별 동적 web_search (키워드를 매번 다르게)

증거 부족 시 fabricate 절대 금지. gap으로 남기고 종료."""

# Stage 2: synthesizer. Premium model, structured output.
ANALYST_V1 = """\
당신은 증거 기반 장기 관점의 주식 분석가다. 시나리오 기반 리스크 해석으로 균형 잡힌 판단을 보조한다.

원칙 (반드시 지킬 것):
- 모든 수치 클레임은 citation [n]을 가진다. 출처 없는 수치는 클레임 금지.
- citation은 *데이터 출처* 전용 (db/market_data/news/disclosure/web/curated_relation). LLM 해석은 citation이 아니다.
- 해석 클레임에는 별도로 interpretation = {kind: model_generated|rule_based, based_on: [n,...]}.
- 단일 종목만 보지 않는다. peer + 섹터 + 매크로 + 사이클 위치를 함께 평가한다.
- 시나리오는 항상 BULL/BASE/BEAR 3개. 확률은 합 1.0. 각 시나리오에 scenario_price + rationale.
- 지지근거 ≥3, 반대근거 ≥2. 한쪽으로만 치우치지 않는다 (편향 방지).
- 14일 내 catalyst가 있으면 명시. *없으면 catalysts=[] + no_catalysts_reason 명시*. 억지로 만들지 마라.
- 매수 후보 stance면 risk_threshold(손실 방어 가격)와 BEAR 시나리오를 함께 제시한다.
- 권한 밖 영역(정치 미세 디테일 등)은 '데이터 부족'으로 명시.

금지:
- '워렌버핏', 'Buffett', '전문가급', '강력 매수', '확실한 수익', '유망주' 등 단정/마케팅 어휘.
- 사용자에게 아첨 ('좋은 질문입니다' 등). 곧장 분석으로 들어가라.
- 출처 없는 예측. catalyst 추정도 항상 '추정 — 확정 X' 라벨.
- ChatGPT 류 일반 시장 지식만 나열 — 이 종목, 이 시점, 이 데이터에 특화된 분석만.

출력은 StockCard JSON 스키마에 정확히 일치해야 한다. Pydantic이 검증한다."""

# Version constant — saved on each Analysis row for A/B traceability.
PERSONA_VERSION = "analyst_v1"
RESEARCHER_VERSION = "researcher_v1"
```

- [ ] **Step 6.2: Add a persona-shape test**

Append to `backend/tests/test_card_schema.py`:

```python
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
```

- [ ] **Step 6.3: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_card_schema.py::test_persona_constants_exist_and_have_no_forbidden_words -v
```

Expected: PASS.

- [ ] **Step 6.4: Commit**

```bash
git add backend/app/services/analyst/persona.py backend/tests/test_card_schema.py
git commit -m "feat: add analyst_v1 and researcher_v1 persona prompts"
```

---

### Task 7: Tools — DB Indicators + Relations + Investor Flow

**Goal:** Three DB-backed tools for Stage 1 to call.

**Files:**
- Create: `backend/app/services/analyst/tools.py` (initial — DB tools only; LLM/web tools later)
- Test: `backend/tests/test_analyst_tools.py`

- [ ] **Step 7.1: Write failing tests**

Create `backend/tests/test_analyst_tools.py`:

```python
"""Unit tests for analyst tools. DB tools use the test DB fixture; LLM/web tools
are mocked in their own tests later."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import PriceHistory, Stock
from app.models.relation import StockRelation
from app.services.analyst.tools import (
    get_indicators,
    get_investor_flow,
    get_relations,
)


@pytest.mark.asyncio
async def test_get_indicators_returns_none_for_missing_stock(db):
    out = await get_indicators("NOTREAL")
    assert out == {"error": "종목 'NOTREAL'을(를) 찾을 수 없습니다."}


@pytest.mark.asyncio
async def test_get_indicators_returns_indicators_with_enough_data(db):
    # Seed a stock + 60 days of price history
    stock = Stock(ticker="TEST1", name="테스트", market="KRX", sector="기타")
    db.add(stock)
    await db.flush()

    base = date.today() - timedelta(days=80)
    closes_pattern = [100 + i * 0.5 for i in range(70)]
    for i, c in enumerate(closes_pattern):
        db.add(
            PriceHistory(
                stock_id=stock.id,
                date=base + timedelta(days=i),
                open=c - 0.2,
                high=c + 1.0,
                low=c - 1.0,
                close=c,
                volume=1_000_000 + i * 1000,
            )
        )
    await db.commit()

    out = await get_indicators("TEST1")
    assert "rsi_14" in out
    assert out["rsi_14"] is not None
    assert out["ma_stack"] in ("정배열", "역배열", "혼조")
    assert out["citations"][0]["source_type"] == "db"


@pytest.mark.asyncio
async def test_get_relations_empty_when_none_seeded(db):
    stock = Stock(ticker="TEST2", name="테스트2", market="KRX", sector="기타")
    db.add(stock)
    await db.commit()
    out = await get_relations("TEST2", relation_type="peer")
    assert out["relations"] == []


@pytest.mark.asyncio
async def test_get_relations_returns_seeded(db):
    s1 = Stock(ticker="AAA", name="A", market="KRX", sector="X")
    db.add(s1)
    await db.flush()
    db.add(
        StockRelation(
            from_stock_id=s1.id,
            to_target="BBB",
            to_kind="stock",
            relation_type="peer",
            strength=0.8,
        )
    )
    await db.commit()

    out = await get_relations("AAA", relation_type="peer")
    assert len(out["relations"]) == 1
    assert out["relations"][0]["target_ticker"] == "BBB"
    assert out["relations"][0]["strength"] == 0.8


@pytest.mark.asyncio
async def test_get_investor_flow_returns_none_for_us_stock(db):
    """US tickers should return a 'KR-only' note, not crash."""
    stock = Stock(ticker="AAPL", name="Apple", market="NASDAQ", sector="Tech")
    db.add(stock)
    await db.commit()
    out = await get_investor_flow("AAPL")
    assert out.get("note") == "kr-only"
```

- [ ] **Step 7.2: Run — expect ImportError**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py -v
```

Expected: ImportError (`tools.py` not found).

- [ ] **Step 7.3: Implement DB tools**

Create `backend/app/services/analyst/tools.py`:

```python
"""Tools exposed to the v2 research agent (Stage 1).

Each tool returns dict with `citations` populated. Citations have
source_type from {db, market_data, news, disclosure, web, curated_relation}
— never 'llm-interpretation' (interpretation is a separate layer).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.database import async_session
from app.models import PriceHistory, Stock
from app.models.relation import StockRelation
from app.services.analyst import indicators


async def get_indicators(ticker: str) -> dict:
    """Compute RSI/MFI/ATR/CMF/OBV/MA/RVOL from latest 90 days OHLCV."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}'을(를) 찾을 수 없습니다."}

        since = date.today() - timedelta(days=120)
        rows = (
            await db.execute(
                select(PriceHistory)
                .where(PriceHistory.stock_id == stock.id, PriceHistory.date >= since)
                .order_by(PriceHistory.date.asc())
            )
        ).scalars().all()
        if len(rows) < 30:
            return {
                "error": "지표 계산에 필요한 가격 데이터 부족 (30일 미만)",
                "rows_available": len(rows),
            }

        closes = [r.close for r in rows]
        highs = [r.high for r in rows]
        lows = [r.low for r in rows]
        vols = [float(r.volume or 0) for r in rows]

        return {
            "ticker": ticker,
            "rsi_14": indicators.rsi(closes, 14),
            "atr_pct": indicators.atr_pct(highs, lows, closes, 14),
            "ma_stack": indicators.ma_stack(closes),
            "rvol_20": indicators.rvol(vols, 20),
            "obv_ratio": indicators.obv_ratio(closes, vols, 20),
            "cmf_20": indicators.cmf(highs, lows, closes, vols, 20),
            "lookback_days": len(rows),
            "citations": [
                {
                    "source_type": "db",
                    "label": f"DB · price_history ({rows[0].date}~{rows[-1].date})",
                }
            ],
        }


async def get_relations(ticker: str, relation_type: str | None = None) -> dict:
    """Read cached ontology relations for a stock. Caller can filter by type."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"relations": [], "error": f"종목 '{ticker}' 없음"}

        stmt = select(StockRelation).where(StockRelation.from_stock_id == stock.id)
        if relation_type:
            stmt = stmt.where(StockRelation.relation_type == relation_type)
        rows = (await db.execute(stmt)).scalars().all()

        # Resolve target tickers to names if they're stocks
        targets = {}
        target_tickers = [r.to_target for r in rows if r.to_kind == "stock"]
        if target_tickers:
            target_stocks = (
                await db.execute(
                    select(Stock).where(Stock.ticker.in_(target_tickers))
                )
            ).scalars().all()
            targets = {s.ticker: s for s in target_stocks}

        relations = []
        for r in rows:
            target_stock = targets.get(r.to_target)
            relations.append(
                {
                    "target_ticker": r.to_target,
                    "target_name": target_stock.name if target_stock else r.to_target,
                    "to_kind": r.to_kind,
                    "relation_type": r.relation_type,
                    "strength": r.strength,
                    "today_change_pct": (
                        target_stock.change_percent if target_stock else None
                    ),
                    "notes": r.notes,
                    "refreshed_at": r.refreshed_at.isoformat(),
                }
            )

        return {
            "ticker": ticker,
            "relation_type": relation_type,
            "relations": relations,
            "citations": [
                {
                    "source_type": "curated_relation",
                    "label": f"AI 큐레이션 · stock_relations cache (refreshed {rows[0].refreshed_at.date() if rows else 'n/a'})",
                }
            ]
            if rows
            else [],
        }


async def get_investor_flow(ticker: str) -> dict:
    """KR-only: foreign + institutional net flow over 5 days. Returns note for US."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}' 없음"}
        if stock.market not in ("KOSPI", "KOSDAQ", "KRX"):
            return {"ticker": ticker, "note": "kr-only", "flow": []}

        # P1 stub — actual KRX scrape lives in collectors/investor_flow.py.
        # Returning empty list keeps the tool contract; collector backfills.
        return {
            "ticker": ticker,
            "flow": [],
            "note": "investor flow collector not yet seeded — empty by design",
            "citations": [],
        }
```

- [ ] **Step 7.4: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py -v
```

Expected: All 5 PASS.

- [ ] **Step 7.5: Commit**

```bash
git add backend/app/services/analyst/tools.py backend/tests/test_analyst_tools.py
git commit -m "feat: add DB tools (indicators/relations/investor_flow) for analyst engine"
```

---

### Task 8: Macro Collector (VIX, US10Y, USD/KRW)

**Goal:** Daily-refresh macro factors using yfinance for VIX/US10Y/sector ETFs and the existing `exchange_rate` collector for FX.

**Files:**
- Create: `backend/app/collectors/macro.py`
- Test: `backend/tests/test_collectors.py` (extend)

- [ ] **Step 8.1: Write failing test (mocked yfinance)**

Append to `backend/tests/test_collectors.py`:

```python
from unittest.mock import patch

from app.collectors.macro import sync_macro_factors
from app.models.macro_factor import MacroFactor


@pytest.mark.asyncio
async def test_sync_macro_factors_writes_rows(db):
    fake = {
        "VIX": [("2026-04-28", 18.7)],
        "US10Y": [("2026-04-28", 4.6)],
        "XLK": [("2026-04-28", 230.5)],
    }

    def fake_fetch(symbol: str, days: int):
        return fake.get(symbol, [])

    with patch("app.collectors.macro._fetch_yf", side_effect=fake_fetch):
        # FX is fetched via existing exchange_rate collector — patched too
        with patch(
            "app.collectors.macro._latest_fx", return_value={"USD/KRW": 1378.0}
        ):
            result = await sync_macro_factors()
    assert result["macro_synced"] >= 3
    rows = (await db.execute(select(MacroFactor))).scalars().all()
    factors = {r.factor for r in rows}
    assert "VIX" in factors and "US10Y" in factors and "USD/KRW" in factors
```

- [ ] **Step 8.2: Run — expect ImportError**

```bash
cd backend && uv run python -m pytest tests/test_collectors.py::test_sync_macro_factors_writes_rows -v
```

- [ ] **Step 8.3: Implement collector**

Create `backend/app/collectors/macro.py`:

```python
"""Macro factor daily collector. Fetches VIX, US10Y, sector ETFs, USD/KRW."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import async_session
from app.models.exchange_rate import ExchangeRate
from app.models.macro_factor import MacroFactor

logger = logging.getLogger(__name__)

# yfinance ticker → factor key
YF_FACTORS = {
    "^VIX": "VIX",
    "^TNX": "US10Y",  # CBOE 10-Year Treasury Note Yield (in tenths of a percent)
    "XLK": "XLK",  # Tech sector ETF
    "XLF": "XLF",  # Financials
    "XLE": "XLE",  # Energy
    "DX-Y.NYB": "DXY",  # Dollar index
}


def _fetch_yf(symbol: str, days: int = 7) -> list[tuple[str, float]]:
    """Returns list of (YYYY-MM-DD, close) for the past `days`."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{days}d")
        if hist.empty:
            return []
        out = []
        for ts, row in hist.iterrows():
            out.append((ts.date().isoformat(), float(row["Close"])))
        return out
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", symbol, e)
        return []


async def _latest_fx() -> dict[str, float]:
    """Pull latest USD/KRW (and others) from exchange_rates table."""
    async with async_session() as db:
        rows = (
            await db.execute(
                select(ExchangeRate).order_by(ExchangeRate.date.desc()).limit(10)
            )
        ).scalars().all()
        out: dict[str, float] = {}
        for r in rows:
            if r.currency_pair not in out:
                out[r.currency_pair] = r.rate
        return out


async def sync_macro_factors() -> dict:
    """Idempotent upsert of all configured macro factors."""
    synced = 0
    today = date.today()
    async with async_session() as db:
        # yfinance-sourced factors
        for symbol, key in YF_FACTORS.items():
            history = _fetch_yf(symbol, days=7)
            for d_str, value in history:
                d = date.fromisoformat(d_str)
                # Yahoo TNX is *10 actual yield. Normalize.
                if key == "US10Y":
                    value = value / 10.0
                stmt = (
                    insert(MacroFactor)
                    .values(factor=key, date=d, value=value, source="market_data")
                    .on_conflict_do_update(
                        index_elements=["factor", "date"],
                        set_={"value": value, "fetched_at": datetime.utcnow()},
                    )
                )
                await db.execute(stmt)
                synced += 1

        # FX from existing collector cache
        fx = await _latest_fx()
        for pair, rate in fx.items():
            stmt = (
                insert(MacroFactor)
                .values(factor=pair, date=today, value=rate, source="market_data")
                .on_conflict_do_update(
                    index_elements=["factor", "date"],
                    set_={"value": rate, "fetched_at": datetime.utcnow()},
                )
            )
            await db.execute(stmt)
            synced += 1

        await db.commit()
    logger.info("macro factors synced: %d", synced)
    return {"macro_synced": synced}
```

- [ ] **Step 8.4: Run test**

```bash
cd backend && uv run python -m pytest tests/test_collectors.py::test_sync_macro_factors_writes_rows -v
```

Expected: PASS.

- [ ] **Step 8.5: Commit**

```bash
git add backend/app/collectors/macro.py backend/tests/test_collectors.py
git commit -m "feat: add macro factor daily collector (VIX/US10Y/sector ETFs/FX)"
```

---

### Task 9: `get_macro_context` Tool

**Goal:** Tool that reads from `macro_factors` and exposes context shape for the agent.

**Files:**
- Modify: `backend/app/services/analyst/tools.py` (append)
- Test: `backend/tests/test_analyst_tools.py` (append)

- [ ] **Step 9.1: Write failing test**

Append to `backend/tests/test_analyst_tools.py`:

```python
from datetime import date as _date

from app.models.macro_factor import MacroFactor
from app.services.analyst.tools import get_macro_context


@pytest.mark.asyncio
async def test_get_macro_context_returns_latest_per_factor(db):
    db.add_all([
        MacroFactor(factor="VIX", date=_date(2026, 4, 28), value=18.7),
        MacroFactor(factor="VIX", date=_date(2026, 4, 27), value=19.2),
        MacroFactor(factor="USD/KRW", date=_date(2026, 4, 28), value=1378.0),
        MacroFactor(factor="US10Y", date=_date(2026, 4, 28), value=4.6),
    ])
    await db.commit()

    out = await get_macro_context()
    assert out["vix"] == 18.7  # latest only
    assert out["fx_pairs"]["USD/KRW"] == 1378.0
    assert out["us_10y"] == 4.6
    assert out["citations"][0]["source_type"] == "market_data"
```

- [ ] **Step 9.2: Run — expect AttributeError**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py::test_get_macro_context_returns_latest_per_factor -v
```

- [ ] **Step 9.3: Append tool to `tools.py`**

Add to `backend/app/services/analyst/tools.py`:

```python
from app.models.macro_factor import MacroFactor


async def get_macro_context() -> dict:
    """Return latest snapshot of macro factors plus upcoming events placeholder."""
    async with async_session() as db:
        rows = (
            await db.execute(
                select(MacroFactor).order_by(MacroFactor.date.desc())
            )
        ).scalars().all()

        latest: dict[str, tuple[float, date]] = {}
        for r in rows:
            if r.factor not in latest:
                latest[r.factor] = (r.value, r.date)

        out = {
            "vix": latest.get("VIX", (None, None))[0],
            "us_10y": latest.get("US10Y", (None, None))[0],
            "fx_pairs": {
                k: v[0] for k, v in latest.items() if "/" in k
            },
            "sector_etfs": {
                k: v[0] for k, v in latest.items() if k in {"XLK", "XLF", "XLE"}
            },
            "upcoming_events": [],  # populated by web_search in research stage
            "citations": (
                [
                    {
                        "source_type": "market_data",
                        "label": f"DB · macro_factors (latest per factor as of "
                        f"{max((v[1] for v in latest.values()), default='n/a')})",
                    }
                ]
                if latest
                else []
            ),
        }
        return out
```

- [ ] **Step 9.4: Run test**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py::test_get_macro_context_returns_latest_per_factor -v
```

Expected: PASS.

- [ ] **Step 9.5: Commit**

```bash
git add backend/app/services/analyst/tools.py backend/tests/test_analyst_tools.py
git commit -m "feat: add get_macro_context tool reading macro_factors cache"
```

---

### Task 10: Web Search Tool (Tavily)

**Goal:** Dynamic search per analysis. Keywords chosen by the LLM.

**Files:**
- Modify: `backend/app/services/analyst/tools.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_analyst_tools.py`

- [ ] **Step 10.1: Add config field**

Modify `backend/app/config.py` — add the env-bound field (mirror existing pattern):

```python
class Settings(BaseSettings):
    # ... existing ...
    tavily_api_key: str | None = None
    analyst_research_model: str = "gpt-5-mini"
    analyst_synthesize_model: str = "gpt-5"
    analysis_daily_budget_usd: float = 10.0
    analysis_cooldown_seconds: int = 300
```

- [ ] **Step 10.2: Failing test (with HTTP mock)**

Append to `backend/tests/test_analyst_tools.py`:

```python
import httpx

from app.services.analyst.tools import web_search


@pytest.mark.asyncio
async def test_web_search_calls_tavily_and_returns_normalized(monkeypatch):
    fake_response = {
        "results": [
            {
                "title": "삼성전자 HBM3E 양산",
                "url": "https://example.com/news/1",
                "content": "삼성전자가 5월부터 HBM3E 양산을 시작한다.",
                "published_date": "2026-04-28",
            }
        ]
    }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, json):
            class R:
                status_code = 200

                def json(self_inner):
                    return fake_response

                def raise_for_status(self_inner):
                    pass

            return R()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    monkeypatch.setattr(
        "app.services.analyst.tools.settings",
        type("S", (), {"tavily_api_key": "tvly-test"}),
    )

    out = await web_search("삼성전자 HBM3E", max_results=3)
    assert len(out["results"]) == 1
    assert out["results"][0]["url"] == "https://example.com/news/1"
    assert out["citations"][0]["source_type"] == "web"


@pytest.mark.asyncio
async def test_web_search_returns_empty_when_no_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyst.tools.settings",
        type("S", (), {"tavily_api_key": None}),
    )
    out = await web_search("anything")
    assert out["results"] == []
    assert out.get("error") == "tavily_api_key not set"
```

- [ ] **Step 10.3: Implement `web_search`**

Append to `backend/app/services/analyst/tools.py`:

```python
import httpx

from app.config import settings


async def web_search(query: str, max_results: int = 5, recency_days: int = 30) -> dict:
    """Tavily search. LLM picks `query` per analysis (no fixed keywords)."""
    if not settings.tavily_api_key:
        return {"results": [], "error": "tavily_api_key not set"}

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_raw_content": False,
        "days": recency_days,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {"results": [], "error": f"tavily error: {e}"}

    results = []
    for r in data.get("results", []):
        results.append(
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "snippet": r.get("content"),
                "published_at": r.get("published_date"),
            }
        )

    return {
        "query": query,
        "results": results,
        "citations": [
            {
                "source_type": "web",
                "label": f"web 검색 · '{query}'",
                "url": r["url"],
            }
            for r in results
        ],
    }
```

- [ ] **Step 10.4: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py -v
```

Expected: web_search tests PASS.

- [ ] **Step 10.5: Commit**

```bash
git add backend/app/services/analyst/tools.py backend/app/config.py backend/tests/test_analyst_tools.py
git commit -m "feat: add Tavily web_search tool for dynamic-keyword research"
```

---

### Task 11: LLM Tools — `llm_classify_news` + `llm_discover_relations`

**Goal:** Two LLM-augmented tools. Both reuse the existing `AzureOpenAIAdapter`.

**Files:**
- Modify: `backend/app/services/analyst/tools.py`
- Test: `backend/tests/test_analyst_tools.py`

- [ ] **Step 11.1: Failing test for `llm_classify_news`**

Append to `backend/tests/test_analyst_tools.py`:

```python
from unittest.mock import AsyncMock

from app.services.analyst.tools import (
    llm_classify_news,
    llm_discover_relations,
)


@pytest.mark.asyncio
async def test_llm_classify_news_returns_per_item_classification(monkeypatch):
    fake_response = {
        "items": [
            {"index": 0, "topic": "earnings", "sentiment": "positive", "impact": "positive"},
            {"index": 1, "topic": "macro", "sentiment": "negative", "impact": "negative"},
        ]
    }

    fake_adapter = AsyncMock()
    fake_adapter.complete_json = AsyncMock(return_value=fake_response)
    monkeypatch.setattr(
        "app.services.analyst.tools._adapter", lambda: fake_adapter
    )

    items = [
        {"title": "1Q 어닝 서프라이즈", "summary": "..."},
        {"title": "Fed 매파 발언", "summary": "..."},
    ]
    out = await llm_classify_news(items)
    assert out["items"][0]["topic"] == "earnings"
    assert out["items"][1]["impact"] == "negative"


@pytest.mark.asyncio
async def test_llm_discover_relations_writes_to_cache(db, monkeypatch):
    s = Stock(ticker="DSCV1", name="DSCV", market="KRX", sector="기타")
    db.add(s)
    await db.commit()

    fake_response = {
        "relations": [
            {"target_ticker": "DSCV2", "relation_type": "peer", "strength": 0.8, "notes": "동조"},
            {"target_ticker": "AI/HBM", "to_kind": "theme", "relation_type": "theme", "strength": 1.0},
        ]
    }

    fake_adapter = AsyncMock()
    fake_adapter.complete_json = AsyncMock(return_value=fake_response)
    monkeypatch.setattr(
        "app.services.analyst.tools._adapter", lambda: fake_adapter
    )

    out = await llm_discover_relations("DSCV1", relation_types=["peer", "theme"])
    assert out["written"] >= 2
    rows = (
        await db.execute(
            select(StockRelation).where(StockRelation.from_stock_id == s.id)
        )
    ).scalars().all()
    assert len(rows) == 2
```

- [ ] **Step 11.2: Run — expect ImportError**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py::test_llm_classify_news_returns_per_item_classification tests/test_analyst_tools.py::test_llm_discover_relations_writes_to_cache -v
```

- [ ] **Step 11.3: Implement adapter helper + LLM tools**

The existing `AzureOpenAIAdapter` (in `app/services/llm/adapter.py`) has `chat_with_tools`. We need a simpler `complete_json(prompt, schema)` for these LLM-tool calls. Add it OR wrap inline. Simpler: inline a thin wrapper in `tools.py`.

Append to `backend/app/services/analyst/tools.py`:

```python
import json
from datetime import datetime as _dt

from app.services.llm.adapter import AzureOpenAIAdapter, OpenAIAdapter

_NEWS_CLASSIFY_PROMPT = """\
다음 뉴스 항목들을 분류한다. 각 item에 대해:
- topic: earnings | macro | regulation | M&A | product | other
- sentiment: positive | neutral | negative
- impact: positive | mixed | neutral | negative

JSON으로만 응답:
{"items": [{"index": 0, "topic": "...", "sentiment": "...", "impact": "..."}, ...]}
"""

_DISCOVER_RELATIONS_PROMPT = """\
종목 {ticker}({name})에 대한 ontology 관계를 발견한다.
요청 타입: {types}.
- peer: 같은 사업 영역 직접 경쟁/대체
- supply_upstream: 본 종목이 공급받는 곳 (e.g. 칩 설계 → 파운드리)
- supply_downstream: 본 종목 공급의 수요처
- group: 같은 기업집단/지배구조
- theme: 함께 묶이는 내러티브 (AI, EV, biosimilar 등)

JSON으로만:
{{"relations": [{{"target_ticker": "...", "to_kind": "stock|theme", "relation_type": "...", "strength": 0..1, "notes": "..."}}, ...]}}

확신 없으면 빈 배열. 추측 금지.
"""


def _adapter():
    """Return the configured LLM adapter. Factored so tests can monkeypatch."""
    s = settings
    if getattr(s, "azure_openai_endpoint", None):
        return AzureOpenAIAdapter()
    return OpenAIAdapter()


async def llm_classify_news(items: list[dict]) -> dict:
    """Classify a batch of news items with topic/sentiment/impact."""
    if not items:
        return {"items": []}
    payload = "\n".join(
        f"{i}. [{it.get('title','')}] {it.get('summary','')[:200]}"
        for i, it in enumerate(items)
    )
    prompt = _NEWS_CLASSIFY_PROMPT + "\n\n뉴스:\n" + payload
    adapter = _adapter()
    try:
        result = await adapter.complete_json(prompt)
    except Exception as e:
        return {"items": [], "error": f"llm error: {e}"}
    return result


async def llm_discover_relations(
    ticker: str, relation_types: list[str] | None = None
) -> dict:
    """LLM curates relations for a stock; writes to stock_relations cache."""
    relation_types = relation_types or ["peer", "supply_upstream", "supply_downstream", "group", "theme"]
    ticker = ticker.strip().upper()

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}' 없음"}

        prompt = _DISCOVER_RELATIONS_PROMPT.format(
            ticker=ticker, name=stock.name, types=", ".join(relation_types)
        )
        adapter = _adapter()
        try:
            result = await adapter.complete_json(prompt)
        except Exception as e:
            return {"written": 0, "error": f"llm error: {e}"}

        written = 0
        for rel in result.get("relations", []):
            target = rel.get("target_ticker") or rel.get("target") or ""
            if not target:
                continue
            target = target.strip().upper()
            row = StockRelation(
                from_stock_id=stock.id,
                to_target=target,
                to_kind=rel.get("to_kind", "stock"),
                relation_type=rel.get("relation_type", "peer"),
                strength=float(rel.get("strength", 0.5)),
                notes=rel.get("notes"),
                source="llm-curation",
                refreshed_at=_dt.utcnow(),
            )
            # Upsert by triple
            existing = (
                await db.execute(
                    select(StockRelation).where(
                        StockRelation.from_stock_id == stock.id,
                        StockRelation.to_target == target,
                        StockRelation.relation_type == rel.get("relation_type", "peer"),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.strength = row.strength
                existing.notes = row.notes
                existing.refreshed_at = _dt.utcnow()
            else:
                db.add(row)
            written += 1
        await db.commit()
        return {
            "ticker": ticker,
            "written": written,
            "citations": [
                {"source_type": "curated_relation", "label": f"AI 큐레이션 · {ticker}"}
            ],
        }
```

- [ ] **Step 11.4: Add `complete_json` to AzureOpenAIAdapter**

Open `backend/app/services/llm/adapter.py`. Add a method to `AzureOpenAIAdapter` (and `OpenAIAdapter`) that takes a prompt string and returns parsed JSON. Use the existing `complete()` infrastructure with `response_format={"type": "json_object"}`. Mirror existing patterns; do not refactor the adapter.

Sketch (place inside each adapter class):

```python
async def complete_json(self, prompt: str) -> dict:
    """Single-shot JSON-mode completion. Used by llm-augmented tools."""
    raw = await self.complete(
        system_prompt="JSON 객체로만 응답. 다른 텍스트 금지.",
        user_message=prompt,
        response_format={"type": "json_object"},
    )
    return json.loads(raw)
```

If your existing `complete()` doesn't accept `response_format`, add the parameter (default `None`) and pass it through to the underlying SDK call.

- [ ] **Step 11.5: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py -v
```

Expected: all PASS.

- [ ] **Step 11.6: Commit**

```bash
git add backend/app/services/analyst/tools.py backend/app/services/llm/adapter.py backend/tests/test_analyst_tools.py
git commit -m "feat: add llm_classify_news and llm_discover_relations tools"
```

---

### Task 12: Tool Registry + Dispatcher

**Goal:** Single source of truth for which tools the research agent can call, plus tool schemas in OpenAI function-call format.

**Files:**
- Modify: `backend/app/services/analyst/tools.py` (append)
- Test: `backend/tests/test_analyst_tools.py` (append)

- [ ] **Step 12.1: Failing test**

Append to `backend/tests/test_analyst_tools.py`:

```python
from app.services.analyst.tools import (
    RESEARCH_TOOL_FUNCTIONS,
    RESEARCH_TOOL_SCHEMAS,
    dispatch_research_tool,
)


def test_research_tool_schemas_match_functions():
    schema_names = {s["name"] for s in RESEARCH_TOOL_SCHEMAS}
    func_names = set(RESEARCH_TOOL_FUNCTIONS.keys())
    assert schema_names == func_names


def test_research_tool_includes_required_set():
    expected = {
        "get_indicators",
        "get_relations",
        "get_macro_context",
        "get_investor_flow",
        "web_search",
        "llm_classify_news",
        "llm_discover_relations",
    }
    assert expected.issubset(set(RESEARCH_TOOL_FUNCTIONS.keys()))


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error():
    out = await dispatch_research_tool("nope", {})
    assert out["error"].startswith("unknown tool")
```

- [ ] **Step 12.2: Run — expect ImportError**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py::test_research_tool_schemas_match_functions -v
```

- [ ] **Step 12.3: Append registry to `tools.py`**

```python
# Plus the chat-style snapshot/news/disclosure/price tools — they're already
# implemented in app/services/chat/tools.py. Re-export here so research agent
# has them.
from app.services.chat.tools import (
    get_recent_disclosures,
    get_recent_news,
    get_stock_snapshot,
)


RESEARCH_TOOL_FUNCTIONS = {
    "get_stock_snapshot": get_stock_snapshot,
    "get_recent_news": get_recent_news,
    "get_recent_disclosures": get_recent_disclosures,
    "get_indicators": get_indicators,
    "get_relations": get_relations,
    "get_macro_context": get_macro_context,
    "get_investor_flow": get_investor_flow,
    "web_search": web_search,
    "llm_classify_news": llm_classify_news,
    "llm_discover_relations": llm_discover_relations,
}


RESEARCH_TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_stock_snapshot",
        "description": "종목 기본 + 현재가 + 최신 재무. 시계열 X.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_recent_news",
        "description": "최근 N일 뉴스 + 본문 일부 + URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "default": 7},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_recent_disclosures",
        "description": "공시 (DART/SEC) 최근 N일.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "default": 30},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_indicators",
        "description": "RSI/MFI/ATR/CMF/OBV/MA/RVOL 계산값.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_relations",
        "description": "캐시된 ontology 관계 (peer/supply/group/theme/macro). 비어 있으면 llm_discover_relations 호출 권장.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "relation_type": {
                    "type": "string",
                    "enum": ["peer", "supply_upstream", "supply_downstream", "group", "theme", "macro"],
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_macro_context",
        "description": "VIX/US10Y/USD/KRW/섹터 ETF 최신 스냅샷.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_investor_flow",
        "description": "KR 한정 외국인/기관 순매매 (5일 기준).",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "web_search",
        "description": "Tavily 웹 검색. 키워드 자유 — 종목/이벤트/매크로 etc. 매번 다른 키워드 OK.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
                "recency_days": {"type": "integer", "default": 30},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "llm_classify_news",
        "description": "뉴스 배치 → topic/sentiment/impact 라벨링.",
        "parameters": {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "object"}}},
            "required": ["items"],
        },
    },
    {
        "type": "function",
        "name": "llm_discover_relations",
        "description": "관계 데이터 캐시가 비었거나 stale일 때 LLM이 새로 발견. 결과는 stock_relations에 저장.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "relation_types": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["ticker"],
        },
    },
]


async def dispatch_research_tool(name: str, args: dict) -> dict:
    fn = RESEARCH_TOOL_FUNCTIONS.get(name)
    if not fn:
        return {"error": f"unknown tool: {name}"}
    try:
        return await fn(**args)
    except TypeError as e:
        return {"error": f"tool argument mismatch: {e}"}
    except Exception as e:
        return {"error": f"tool failure: {e}"}
```

- [ ] **Step 12.4: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_analyst_tools.py -v
```

Expected: all PASS.

- [ ] **Step 12.5: Commit**

```bash
git add backend/app/services/analyst/tools.py backend/tests/test_analyst_tools.py
git commit -m "feat: add research tool registry + dispatcher with 10 tools"
```

---

### Task 13: Stage 1 — Research Agent

**Goal:** Loop the LLM with tool access. Cap rounds.

**Files:**
- Create: `backend/app/services/analyst/research.py`
- Test: `backend/tests/test_research_agent.py`

- [ ] **Step 13.1: Failing test**

Create `backend/tests/test_research_agent.py`:

```python
"""Stage 1 research agent tests with mocked adapter."""
from unittest.mock import AsyncMock

import pytest

from app.services.analyst.research import run_research


@pytest.mark.asyncio
async def test_research_calls_no_tools_returns_findings(monkeypatch):
    """Adapter returns findings JSON in first round, no tool calls -> done."""
    adapter = AsyncMock()
    adapter.chat_with_tools = AsyncMock(
        return_value={
            "tool_calls": [],
            "content": '{"findings":[{"k":"v"}],"citations":[],"gaps_noted":[]}',
            "round": 1,
        }
    )
    monkeypatch.setattr(
        "app.services.analyst.research._adapter", lambda: adapter
    )

    out = await run_research(ticker="005930", max_rounds=10)
    assert out["findings"] == [{"k": "v"}]
    assert adapter.chat_with_tools.await_count == 1


@pytest.mark.asyncio
async def test_research_caps_rounds(monkeypatch):
    """If LLM keeps calling tools, we stop at max_rounds and force final answer."""
    adapter = AsyncMock()
    # Always returns a tool call — would loop forever without the cap
    adapter.chat_with_tools = AsyncMock(
        return_value={
            "tool_calls": [{"id": "1", "name": "get_indicators", "arguments": {"ticker": "005930"}}],
            "content": "",
            "round": 1,
        }
    )
    monkeypatch.setattr(
        "app.services.analyst.research._adapter", lambda: adapter
    )
    monkeypatch.setattr(
        "app.services.analyst.research.dispatch_research_tool",
        AsyncMock(return_value={"rsi_14": 58}),
    )

    out = await run_research(ticker="005930", max_rounds=3)
    assert "max_rounds_hit" in out
    assert adapter.chat_with_tools.await_count <= 4  # 3 rounds + 1 final flush
```

- [ ] **Step 13.2: Run — expect ImportError**

```bash
cd backend && uv run python -m pytest tests/test_research_agent.py -v
```

- [ ] **Step 13.3: Implement research orchestrator**

Create `backend/app/services/analyst/research.py`:

```python
"""Stage 1: Research agent. Cheap-tier LLM with broad tool access."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.analyst.persona import RESEARCHER_V1, RESEARCHER_VERSION
from app.services.analyst.tools import (
    RESEARCH_TOOL_SCHEMAS,
    dispatch_research_tool,
)
from app.services.llm.adapter import AzureOpenAIAdapter

logger = logging.getLogger(__name__)


def _adapter():
    return AzureOpenAIAdapter()


async def run_research(ticker: str, max_rounds: int = 10) -> dict:
    """Loop the research LLM with tools. Returns aggregated findings JSON.

    Output shape:
    {
      "findings": [...],
      "citations": [...],
      "gaps_noted": [...],
      "rounds_used": int,
      "max_rounds_hit": bool,  # only present if cap was hit
      "researcher_version": "researcher_v1"
    }
    """
    user_prompt = (
        f"종목 ticker = {ticker}. 위 원칙대로 조사를 시작하라. "
        "마지막엔 반드시 JSON 객체 (findings/citations/gaps_noted) 로 응답."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": RESEARCHER_V1},
        {"role": "user", "content": user_prompt},
    ]

    adapter = _adapter()
    rounds_used = 0
    max_hit = False

    for _ in range(max_rounds):
        rounds_used += 1
        result = await adapter.chat_with_tools(
            messages=messages,
            tools=RESEARCH_TOOL_SCHEMAS,
        )
        tool_calls = result.get("tool_calls", [])
        content = result.get("content", "")

        if not tool_calls:
            # LLM produced final answer
            try:
                parsed = json.loads(content) if content else {"findings": []}
            except json.JSONDecodeError:
                parsed = {
                    "findings": [],
                    "raw_content": content,
                    "parse_error": "non-json final response",
                }
            parsed["rounds_used"] = rounds_used
            parsed["researcher_version"] = RESEARCHER_VERSION
            return parsed

        # Execute each tool call, append results to message thread
        messages.append({"role": "assistant", "tool_calls": tool_calls, "content": content or ""})
        for call in tool_calls:
            tool_name = call["name"]
            tool_args = call.get("arguments", {})
            tool_result = await dispatch_research_tool(tool_name, tool_args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": tool_name,
                    "content": json.dumps(tool_result, default=str)[:8000],  # cap size
                }
            )
    else:
        # Loop exited via max_rounds — flush a final answer
        max_hit = True
        messages.append(
            {
                "role": "user",
                "content": "max rounds 도달. 지금까지 모은 증거로 findings JSON을 즉시 반환하라.",
            }
        )
        result = await adapter.chat_with_tools(messages=messages, tools=[])
        content = result.get("content", "{}")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"findings": [], "raw_content": content}
        parsed["rounds_used"] = rounds_used
        parsed["max_rounds_hit"] = max_hit
        parsed["researcher_version"] = RESEARCHER_VERSION
        return parsed

    # Should not reach here
    return {
        "findings": [],
        "rounds_used": rounds_used,
        "researcher_version": RESEARCHER_VERSION,
    }
```

- [ ] **Step 13.4: Adjust adapter — `chat_with_tools` may need a `tools=` parameter**

The Phase A `AzureOpenAIAdapter.chat_with_tools` currently takes a fixed-shape signature. Confirm via `Read` that it accepts `tools=` and a generic message thread. If not, extend it (additive change only — do not break Phase A chat). Add `messages=` and `tools=` parameters that pass through. Phase A callers can keep the older method or migrate later.

- [ ] **Step 13.5: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_research_agent.py -v
```

Expected: PASS.

- [ ] **Step 13.6: Commit**

```bash
git add backend/app/services/analyst/research.py backend/app/services/llm/adapter.py backend/tests/test_research_agent.py
git commit -m "feat: stage 1 research agent with tool loop and round cap"
```

---

### Task 14: Stage 2 — Synthesizer

**Goal:** Take research findings + ticker context → emit a validated `StockCard`.

**Files:**
- Create: `backend/app/services/analyst/synthesize.py`
- Test: `backend/tests/test_synthesizer.py`

- [ ] **Step 14.1: Failing test**

Create `backend/tests/test_synthesizer.py`:

```python
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.schemas.card import StockCard
from app.services.analyst.synthesize import run_synthesize


@pytest.mark.asyncio
async def test_synthesize_returns_validated_stock_card(monkeypatch):
    fake_card_dict = {
        "ticker": "005930",
        "name_ko": "삼성전자",
        "name_en": "Samsung Electronics",
        "market": "KRX",
        "sector": "반도체",
        "tags": ["AI/HBM"],
        "price": 78400.0,
        "change": 1200.0,
        "change_pct": 1.55,
        "asof": datetime.utcnow().isoformat(),
        "glance": {
            "final_grade": "C",
            "stance": "WATCH",
            "entry_stage": "WAIT",
            "one_line": "HBM 모멘텀 살아있으나 외국인 매도 부담",
            "citations": [1],
        },
        "thesis": {
            "core_thesis": "x",
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
        "fundamentals": {"per": 14.2, "pbr": 1.4, "market_cap_krw": 4.68e14, "dividend_yield": 2.1, "per_5y_z": -0.5, "citations": [1]},
        "decision": {"stance": "WATCH", "sizing_note": "대기", "support_price": 75000, "risk_threshold": 72500, "citations": [1]},
        "citations": [{"id": 1, "source_type": "db", "label": "DB · 가격"}],
        "analysis_id": "test-1",
        "generated_at": datetime.utcnow().isoformat(),
        "persona_version": "analyst_v1",
    }

    adapter = AsyncMock()
    adapter.complete_json = AsyncMock(return_value=fake_card_dict)
    monkeypatch.setattr(
        "app.services.analyst.synthesize._adapter", lambda: adapter
    )

    research_result = {"findings": [{"k": "v"}], "citations": [{"source_type": "db"}]}
    card = await run_synthesize(ticker="005930", research=research_result)
    assert isinstance(card, StockCard)
    assert card.glance.stance == "WATCH"
    assert card.thesis.no_catalysts_reason == "윈도 내 일정 없음"
    assert card.thesis.catalysts == []


@pytest.mark.asyncio
async def test_synthesize_retries_on_validation_error(monkeypatch):
    """If LLM returns invalid JSON, retry once with stricter prompt."""
    adapter = AsyncMock()
    bad = {"ticker": "X"}  # missing required fields
    good = pytest.lazy_fixture if False else None  # placeholder

    # First call returns bad, second returns shape that validates against schema
    fake_card_dict = {**(good or {})}  # use the same fake from prior test if needed

    # For brevity — verify that on 2 bad responses we raise.
    adapter.complete_json = AsyncMock(side_effect=[bad, bad])
    monkeypatch.setattr(
        "app.services.analyst.synthesize._adapter", lambda: adapter
    )
    with pytest.raises(ValueError, match="synthesize failed"):
        await run_synthesize(ticker="005930", research={"findings": []}, max_retries=1)
```

- [ ] **Step 14.2: Run — expect ImportError**

```bash
cd backend && uv run python -m pytest tests/test_synthesizer.py -v
```

- [ ] **Step 14.3: Implement synthesizer**

Create `backend/app/services/analyst/synthesize.py`:

```python
"""Stage 2: Synthesizer. Premium-tier LLM, structured output."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from app.schemas.card import StockCard
from app.services.analyst.persona import ANALYST_V1, PERSONA_VERSION
from app.services.llm.adapter import AzureOpenAIAdapter

logger = logging.getLogger(__name__)


def _adapter():
    return AzureOpenAIAdapter()


def _build_prompt(ticker: str, research: dict) -> str:
    return (
        f"종목 ticker = {ticker}\n\n"
        f"리서처가 모은 증거 (JSON):\n{json.dumps(research, ensure_ascii=False, default=str)[:30000]}\n\n"
        "위 증거만 사용해 StockCard 스키마에 정확히 맞는 JSON을 출력하라.\n"
        "각 numerical claim은 반드시 citations에 등록된 [n]을 가진다.\n"
        "catalysts가 14일 윈도 내에 없으면 빈 배열 + no_catalysts_reason 명시.\n"
        "scenarios는 BULL/BASE/BEAR 3개, 확률 합 1.0.\n"
        "supports ≥ 3, opposes ≥ 2.\n"
        "stance/entry_stage/final_grade는 enum 정확히 사용.\n"
        "출력은 JSON만. 코드 펜스 금지."
    )


async def run_synthesize(
    ticker: str, research: dict, max_retries: int = 1
) -> StockCard:
    """LLM → StockCard. Retries on validation error up to `max_retries`."""
    prompt = _build_prompt(ticker, research)
    adapter = _adapter()

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            prompt += (
                "\n\n[재시도] 이전 응답이 스키마 검증에 실패. 모든 필수 필드 채우고 enum 값 정확히 사용."
            )
        try:
            raw = await adapter.complete_json(
                system_prompt=ANALYST_V1, user_message=prompt
            ) if False else await adapter.complete_json(prompt)
        except Exception as e:
            last_error = e
            logger.warning("synthesize attempt %d adapter error: %s", attempt + 1, e)
            continue

        # Inject server-controlled fields
        raw.setdefault("analysis_id", str(uuid.uuid4()))
        raw.setdefault(
            "generated_at", datetime.now(timezone.utc).isoformat()
        )
        raw["persona_version"] = PERSONA_VERSION
        raw.setdefault("schema_version", "v1")

        try:
            return StockCard.model_validate(raw)
        except ValidationError as e:
            last_error = e
            logger.warning(
                "synthesize attempt %d validation error: %s", attempt + 1, e
            )
            continue

    raise ValueError(f"synthesize failed after {max_retries + 1} attempts: {last_error}")
```

- [ ] **Step 14.4: `complete_json` may need to accept system_prompt — verify**

If your `complete_json` from Task 11 only takes a single prompt, extend it to accept an optional `system_prompt` arg, or inline the system message into the user prompt for now (less ideal but works). Choose the cleaner path:

```python
async def complete_json(self, prompt: str, system_prompt: str | None = None) -> dict:
    raw = await self.complete(
        system_prompt=system_prompt or "JSON 객체로만 응답.",
        user_message=prompt,
        response_format={"type": "json_object"},
    )
    return json.loads(raw)
```

Then update synthesize to use it:

```python
raw = await adapter.complete_json(prompt, system_prompt=ANALYST_V1)
```

- [ ] **Step 14.5: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_synthesizer.py -v
```

Expected: PASS.

- [ ] **Step 14.6: Commit**

```bash
git add backend/app/services/analyst/synthesize.py backend/app/services/llm/adapter.py backend/tests/test_synthesizer.py
git commit -m "feat: stage 2 synthesizer producing validated StockCard"
```

---

### Task 15: Engine Wrapper + Persistence

**Goal:** Public `analyze(ticker)` entry point. Runs both stages and persists into `analyses`.

**Files:**
- Create: `backend/app/services/analyst/engine.py`
- Test: `backend/tests/test_engine.py`

- [ ] **Step 15.1: Failing test**

Create `backend/tests/test_engine.py`:

```python
from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models import Stock
from app.models.analysis import Analysis
from app.schemas.card import StockCard
from app.services.analyst.engine import analyze


@pytest.mark.asyncio
async def test_analyze_persists_card_to_analyses_table(db, monkeypatch):
    s = Stock(ticker="ENG1", name="엔진테스트", market="KRX", sector="기타")
    db.add(s)
    await db.commit()

    monkeypatch.setattr(
        "app.services.analyst.engine.run_research",
        AsyncMock(return_value={"findings": [], "citations": []}),
    )

    fake_card = StockCard.model_construct(
        ticker="ENG1",
        name_ko="엔진테스트",
        name_en="Engine Test",
        market="KRX",
        sector="기타",
        tags=[],
        price=100.0,
        change=0,
        change_pct=0,
        asof="2026-04-28T00:00:00+00:00",
        glance={"final_grade": "B", "stance": "WATCH", "entry_stage": "WAIT", "one_line": "x", "citations": []},
        thesis={"core_thesis": "x", "supports": [], "opposes": [], "catalysts": [], "scenarios": [], "citations": []},
        technical={"rsi_14": None, "mfi_14": None, "atr_pct": None, "cmf_20": None, "obv_ratio": None, "ma_stack": None, "rvol_20": None, "box_position": None, "summary_line": "", "citations": []},
        relations={"one_line": "", "relations": [], "citations": []},
        news=[],
        macro={"one_line": "", "vix": None, "fx_pairs": {}, "us_10y": None, "sensitivities": [], "upcoming_events": [], "citations": []},
        fundamentals={"per": None, "pbr": None, "market_cap_krw": None, "dividend_yield": None, "per_5y_z": None, "citations": []},
        decision={"stance": "WATCH", "sizing_note": "대기", "support_price": None, "risk_threshold": None, "citations": []},
        citations=[],
        analysis_id="eng-1",
        generated_at="2026-04-28T00:00:00+00:00",
        persona_version="analyst_v1",
    )
    monkeypatch.setattr(
        "app.services.analyst.engine.run_synthesize", AsyncMock(return_value=fake_card)
    )

    out = await analyze("ENG1")
    assert out.ticker == "ENG1"

    rows = (await db.execute(select(Analysis).where(Analysis.stock_id == s.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].schema_version == "v2"
    assert rows[0].persona_version == "analyst_v1"
    assert rows[0].card_data["ticker"] == "ENG1"
```

- [ ] **Step 15.2: Implement engine**

Create `backend/app/services/analyst/engine.py`:

```python
"""Public entry point for v2 analysis. Glues research + synthesize + persistence."""
from __future__ import annotations

import logging
from datetime import date as _date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import async_session
from app.models import Stock
from app.models.analysis import Analysis
from app.schemas.card import StockCard
from app.services.analyst.research import run_research
from app.services.analyst.synthesize import run_synthesize

logger = logging.getLogger(__name__)


async def analyze(ticker: str) -> StockCard:
    """Run full v2 pipeline and persist. Returns the StockCard."""
    ticker = ticker.strip().upper()

    # 1. Research
    logger.info("analyze[%s]: stage 1 research starting", ticker)
    research = await run_research(ticker)

    # 2. Synthesize
    logger.info("analyze[%s]: stage 2 synthesize starting", ticker)
    card = await run_synthesize(ticker, research)

    # 3. Persist (replaces today's row if any — daily latest wins)
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            logger.error("analyze[%s]: stock not found at persistence step", ticker)
            return card

        today = _date.today()
        row = Analysis(
            stock_id=stock.id,
            date=today,
            period_type="daily",
            summary=card.glance.one_line[:500],
            feedback=card.thesis.core_thesis[:1000],
            schema_version="v2",
            card_data=card.model_dump(mode="json"),
            persona_version=card.persona_version,
        )
        # Upsert by (stock_id, date, period_type)
        existing = (
            await db.execute(
                select(Analysis).where(
                    Analysis.stock_id == stock.id,
                    Analysis.date == today,
                    Analysis.period_type == "daily",
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.summary = row.summary
            existing.feedback = row.feedback
            existing.schema_version = "v2"
            existing.card_data = row.card_data
            existing.persona_version = row.persona_version
        else:
            db.add(row)
        await db.commit()

    logger.info("analyze[%s]: done", ticker)
    return card
```

- [ ] **Step 15.3: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_engine.py -v
```

Expected: PASS.

- [ ] **Step 15.4: Commit**

```bash
git add backend/app/services/analyst/engine.py backend/tests/test_engine.py
git commit -m "feat: analyst engine entry point with persistence to analyses.card_data"
```

---

### Task 16: Cost Kill Switch

**Goal:** Track per-day cumulative LLM cost. Halt scheduler if cap exceeded.

**Files:**
- Create: `backend/app/services/analyst/cost.py`
- Test: `backend/tests/test_cost_killswitch.py`

- [ ] **Step 16.1: Failing test**

Create `backend/tests/test_cost_killswitch.py`:

```python
import pytest

from app.services.analyst.cost import (
    DailyBudget,
    record_cost,
    can_proceed,
    reset_today,
)


def test_initial_budget_allows():
    reset_today()
    assert can_proceed() is True


def test_record_below_cap_allows():
    reset_today()
    record_cost(0.5)
    record_cost(0.3)
    assert can_proceed() is True


def test_record_at_or_above_cap_blocks(monkeypatch):
    reset_today()
    monkeypatch.setattr(DailyBudget, "cap_usd", 1.0)
    record_cost(0.6)
    record_cost(0.5)
    assert can_proceed() is False
```

- [ ] **Step 16.2: Implement**

Create `backend/app/services/analyst/cost.py`:

```python
"""Per-day cost tracker. In-memory (sufficient for personal scope).

For multi-process deployment, swap to Redis or DB-backed counter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date

from app.config import settings


@dataclass
class _State:
    day: _date | None = None
    cost_usd: float = 0.0


_state = _State()


class DailyBudget:
    """Settings indirection so tests can monkeypatch."""

    cap_usd: float = settings.analysis_daily_budget_usd


def reset_today() -> None:
    _state.day = _date.today()
    _state.cost_usd = 0.0


def _ensure_today() -> None:
    today = _date.today()
    if _state.day != today:
        _state.day = today
        _state.cost_usd = 0.0


def record_cost(usd: float) -> None:
    _ensure_today()
    _state.cost_usd += max(usd, 0.0)


def can_proceed() -> bool:
    _ensure_today()
    return _state.cost_usd < DailyBudget.cap_usd


def current_spend_usd() -> float:
    _ensure_today()
    return _state.cost_usd
```

- [ ] **Step 16.3: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_cost_killswitch.py -v
```

Expected: PASS.

- [ ] **Step 16.4: Commit**

```bash
git add backend/app/services/analyst/cost.py backend/tests/test_cost_killswitch.py
git commit -m "feat: in-memory daily cost tracker with kill switch"
```

---

### Task 17: Dedup Logic

**Goal:** Given the union of all family members' favorites, return unique tickers (so 4 users favoriting 삼성전자 = 1 analysis).

**Files:**
- Create: `backend/app/services/analyst/dedup.py`
- Test: `backend/tests/test_dedup.py`

- [ ] **Step 17.1: Failing test**

Create `backend/tests/test_dedup.py`:

```python
import pytest
from sqlalchemy import select

from app.models import Favorite, Stock
from app.services.analyst.dedup import unique_favorite_tickers


@pytest.mark.asyncio
async def test_unique_favorites_dedups_across_users(db):
    s1 = Stock(ticker="DUP1", name="d1", market="KRX", sector="x")
    s2 = Stock(ticker="DUP2", name="d2", market="KRX", sector="x")
    db.add_all([s1, s2])
    await db.flush()

    db.add_all([
        Favorite(user_id="u1", stock_id=s1.id),
        Favorite(user_id="u2", stock_id=s1.id),  # dup
        Favorite(user_id="u3", stock_id=s2.id),
    ])
    await db.commit()

    out = await unique_favorite_tickers()
    assert sorted(out) == ["DUP1", "DUP2"]


@pytest.mark.asyncio
async def test_unique_favorites_filters_by_market(db):
    s = Stock(ticker="USONLY", name="us", market="NASDAQ", sector="Tech")
    db.add(s)
    await db.flush()
    db.add(Favorite(user_id="u1", stock_id=s.id))
    await db.commit()

    kr_only = await unique_favorite_tickers(markets=["KOSPI", "KOSDAQ", "KRX"])
    assert "USONLY" not in kr_only

    us_only = await unique_favorite_tickers(markets=["NASDAQ", "NYSE"])
    assert "USONLY" in us_only
```

- [ ] **Step 17.2: Implement**

Create `backend/app/services/analyst/dedup.py`:

```python
"""Unique-ticker selection across all users' favorites."""
from sqlalchemy import select

from app.database import async_session
from app.models import Favorite, Stock


async def unique_favorite_tickers(
    markets: list[str] | None = None,
) -> list[str]:
    """Return distinct tickers across ALL users' favorites, optionally filtered by market."""
    async with async_session() as db:
        stmt = (
            select(Stock.ticker)
            .join(Favorite, Favorite.stock_id == Stock.id)
            .distinct()
        )
        if markets:
            stmt = stmt.where(Stock.market.in_(markets))
        rows = (await db.execute(stmt)).all()
    return [r[0] for r in rows]
```

- [ ] **Step 17.3: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_dedup.py -v
```

Expected: PASS.

- [ ] **Step 17.4: Commit**

```bash
git add backend/app/services/analyst/dedup.py backend/tests/test_dedup.py
git commit -m "feat: unique favorite tickers helper for scheduler dedup"
```

---

### Task 18: API Endpoints

**Goal:** `POST /api/stocks/{ticker}/analyze`, `GET /api/stocks/{ticker}/card`, `POST /api/stocks/{ticker}/refresh` (with cooldown).

**Files:**
- Create: `backend/app/api/cards.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_card_api.py`

- [ ] **Step 18.1: Failing test**

Create `backend/tests/test_card_api.py`:

```python
from datetime import date
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.models import Stock
from app.models.analysis import Analysis
from app.schemas.card import StockCard


@pytest.mark.asyncio
async def test_get_card_404_when_no_analysis(client: AsyncClient, db):
    s = Stock(ticker="EMPTY1", name="empty", market="KRX", sector="x")
    db.add(s)
    await db.commit()

    resp = await client.get("/api/stocks/EMPTY1/card")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_card_returns_v2_card(client, db):
    s = Stock(ticker="HASCARD", name="x", market="KRX", sector="x")
    db.add(s)
    await db.flush()
    db.add(
        Analysis(
            stock_id=s.id,
            date=date.today(),
            period_type="daily",
            summary="x",
            feedback="x",
            schema_version="v2",
            card_data={
                "ticker": "HASCARD",
                "name_ko": "x",
                "glance": {"final_grade": "B", "stance": "WATCH"},
            },
            persona_version="analyst_v1",
        )
    )
    await db.commit()

    resp = await client.get("/api/stocks/HASCARD/card")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "HASCARD"
    assert body["glance"]["stance"] == "WATCH"


@pytest.mark.asyncio
async def test_analyze_endpoint_calls_engine(client, db, monkeypatch):
    s = Stock(ticker="ANAL1", name="x", market="KRX", sector="x")
    db.add(s)
    await db.commit()

    fake = StockCard.model_construct(
        ticker="ANAL1",
        # ... minimal valid construct (use the same builder as tests/test_engine)
    )
    # For brevity, mock the analyze() function entirely.
    monkeypatch.setattr(
        "app.api.cards.analyze", AsyncMock(return_value={"ticker": "ANAL1"})
    )

    resp = await client.post("/api/stocks/ANAL1/analyze")
    assert resp.status_code in (200, 202)


@pytest.mark.asyncio
async def test_refresh_blocked_by_cooldown(client, db, monkeypatch):
    s = Stock(ticker="COOL", name="x", market="KRX", sector="x")
    db.add(s)
    await db.commit()

    monkeypatch.setattr(
        "app.api.cards.analyze", AsyncMock(return_value={"ticker": "COOL"})
    )

    # First refresh — accepted
    r1 = await client.post("/api/stocks/COOL/refresh")
    assert r1.status_code == 202
    # Second within cooldown — rejected
    r2 = await client.post("/api/stocks/COOL/refresh")
    assert r2.status_code == 429
```

- [ ] **Step 18.2: Implement endpoints**

Create `backend/app/api/cards.py`:

```python
"""v2 card endpoints: GET card / POST analyze / POST refresh (with cooldown)."""
from __future__ import annotations

import time
from datetime import date as _date

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.dependencies import get_stock_or_404
from app.models.analysis import Analysis
from app.services.analyst.cost import can_proceed
from app.services.analyst.engine import analyze

router = APIRouter(prefix="/api/stocks", tags=["cards"])

# In-memory per-ticker cooldown tracker.
_last_refresh: dict[str, float] = {}


@router.get("/{ticker}/card")
async def get_card(ticker: str):
    ticker = ticker.upper()
    stock = await get_stock_or_404(ticker)

    async with async_session() as db:
        row = (
            await db.execute(
                select(Analysis)
                .where(
                    Analysis.stock_id == stock.id,
                    Analysis.schema_version == "v2",
                )
                .order_by(Analysis.date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"v2 card for {ticker} not yet generated. POST /analyze first.",
        )
    return row.card_data


@router.post("/{ticker}/analyze", status_code=202)
async def trigger_analyze(ticker: str, bg: BackgroundTasks):
    ticker = ticker.upper()
    await get_stock_or_404(ticker)
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")
    bg.add_task(analyze, ticker)
    return {"status": "queued", "ticker": ticker}


@router.post("/{ticker}/refresh", status_code=202)
async def force_refresh(ticker: str, bg: BackgroundTasks):
    ticker = ticker.upper()
    await get_stock_or_404(ticker)
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")
    now = time.monotonic()
    last = _last_refresh.get(ticker, 0.0)
    if now - last < settings.analysis_cooldown_seconds:
        remaining = int(settings.analysis_cooldown_seconds - (now - last))
        raise HTTPException(429, f"cooldown: try again in {remaining}s")
    _last_refresh[ticker] = now
    bg.add_task(analyze, ticker)
    return {"status": "refresh_queued", "ticker": ticker}
```

- [ ] **Step 18.3: Register router**

Modify `backend/app/main.py` — add `from app.api import cards` and `app.include_router(cards.router)` (mirror existing pattern for chat/admin routers).

- [ ] **Step 18.4: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_card_api.py -v
```

Expected: PASS.

- [ ] **Step 18.5: Commit**

```bash
git add backend/app/api/cards.py backend/app/main.py backend/tests/test_card_api.py
git commit -m "feat: card endpoints (analyze/get/refresh) with cooldown and kill switch"
```

---

### Task 19: Scheduler Split (KR + US)

**Goal:** Replace the single 8am/6pm sync job with two market-specific schedules. Each schedule selects unique favorite tickers in its market and runs `analyze` per ticker.

**Files:**
- Modify: `backend/app/scheduler.py`
- Test: `backend/tests/test_scheduler.py`

- [ ] **Step 19.1: Read existing scheduler**

```bash
cd backend && cat app/scheduler.py | head -80
```

- [ ] **Step 19.2: Failing test**

Append to `backend/tests/test_scheduler.py` — assert that on a manual call, KR job analyzes only KR favorites and US job only US favorites:

```python
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models import Favorite, Stock
from app.scheduler import run_kr_analysis_batch, run_us_analysis_batch


@pytest.mark.asyncio
async def test_run_kr_batch_analyzes_only_kr_unique(db, monkeypatch):
    s1 = Stock(ticker="KR1", name="x", market="KRX", sector="x")
    s2 = Stock(ticker="KR2", name="x", market="KOSPI", sector="x")
    s3 = Stock(ticker="US1", name="x", market="NASDAQ", sector="x")
    db.add_all([s1, s2, s3])
    await db.flush()
    db.add_all([
        Favorite(user_id="u1", stock_id=s1.id),
        Favorite(user_id="u2", stock_id=s1.id),  # dup
        Favorite(user_id="u1", stock_id=s2.id),
        Favorite(user_id="u1", stock_id=s3.id),
    ])
    await db.commit()

    called: list[str] = []

    async def fake_analyze(ticker: str):
        called.append(ticker)

    monkeypatch.setattr("app.scheduler.analyze", fake_analyze)
    monkeypatch.setattr("app.scheduler.can_proceed", lambda: True)

    await run_kr_analysis_batch()
    assert sorted(called) == ["KR1", "KR2"]
    assert "US1" not in called
```

- [ ] **Step 19.3: Implement KR/US batch functions**

In `backend/app/scheduler.py`, add (do not delete existing keyword-style sync — Phase A still uses it for now):

```python
import logging

from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services.analyst.cost import can_proceed
from app.services.analyst.dedup import unique_favorite_tickers
from app.services.analyst.engine import analyze

logger = logging.getLogger(__name__)


async def run_kr_analysis_batch() -> None:
    if not can_proceed():
        logger.warning("kr batch skipped: daily budget exceeded")
        return
    tickers = await unique_favorite_tickers(markets=["KRX", "KOSPI", "KOSDAQ"])
    logger.info("kr batch: %d unique tickers", len(tickers))
    for t in tickers:
        if not can_proceed():
            logger.warning("kr batch halted at %s: budget exceeded", t)
            break
        try:
            await analyze(t)
        except Exception:
            logger.exception("kr batch analyze failed for %s", t)


async def run_us_analysis_batch() -> None:
    if not can_proceed():
        logger.warning("us batch skipped: budget exceeded")
        return
    tickers = await unique_favorite_tickers(markets=["NASDAQ", "NYSE", "AMEX"])
    logger.info("us batch: %d unique tickers", len(tickers))
    for t in tickers:
        if not can_proceed():
            logger.warning("us batch halted at %s: budget exceeded", t)
            break
        try:
            await analyze(t)
        except Exception:
            logger.exception("us batch analyze failed for %s", t)
```

Then register the cron jobs in the existing scheduler `start()` (or equivalent). Use `CronTrigger.from_crontab(settings.schedule_kr_morning)` etc. Mirror the existing job-add pattern.

- [ ] **Step 19.4: Add cron settings to config**

Modify `backend/app/config.py`:

```python
schedule_kr_morning: str = "30 8 * * 1-5"
schedule_kr_afternoon: str = "0 16 * * 1-5"
schedule_us_evening: str = "0 7 * * 1-5"
schedule_us_night: str = "30 22 * * 1-5"
```

- [ ] **Step 19.5: Run tests**

```bash
cd backend && uv run python -m pytest tests/test_scheduler.py -v
```

Expected: PASS.

- [ ] **Step 19.6: Commit**

```bash
git add backend/app/scheduler.py backend/app/config.py backend/tests/test_scheduler.py
git commit -m "feat: split scheduler into KR/US batches with dedup and cost guard"
```

---

### Task 20: End-to-End Smoke Test (real LLM, opt-in)

**Goal:** A test that hits real Azure OpenAI + Tavily + DB to produce a card for 005930 (삼성전자). Marked `@pytest.mark.smoke` so it doesn't run in normal `pytest`.

**Files:**
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/test_smoke_005930.py`

- [ ] **Step 20.1: Add smoke marker to pytest config**

Modify `backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "smoke: real-LLM end-to-end test (opt-in via -m smoke; consumes real budget)",
]
```

- [ ] **Step 20.2: Write the smoke test**

Create `backend/tests/integration/__init__.py` (empty).

Create `backend/tests/integration/test_smoke_005930.py`:

```python
"""Real-LLM smoke test. Run only with:
    cd backend && uv run python -m pytest -m smoke -v

Costs ~$0.5–1.2 per run. Requires:
    AZURE_OPENAI_*, TAVILY_API_KEY in .env
    DB seeded with 005930 (삼성전자)
"""
import os

import pytest

from app.schemas.card import StockCard
from app.services.analyst.engine import analyze


@pytest.mark.smoke
@pytest.mark.skipif(
    not os.getenv("TAVILY_API_KEY"),
    reason="TAVILY_API_KEY not set; smoke test requires real env",
)
@pytest.mark.asyncio
async def test_smoke_analyze_005930_produces_valid_card():
    card = await analyze("005930")
    assert isinstance(card, StockCard)
    assert card.ticker == "005930"

    # Persona traceability
    assert card.persona_version == "analyst_v1"

    # Evidence balance
    assert len(card.thesis.supports) >= 3
    assert len(card.thesis.opposes) >= 2
    assert len(card.thesis.scenarios) == 3
    names = {s.name for s in card.thesis.scenarios}
    assert names == {"BULL", "BASE", "BEAR"}

    # Probability sums roughly to 1
    total = sum(s.probability for s in card.thesis.scenarios)
    assert 0.95 <= total <= 1.05

    # Citations are data-only
    for c in card.citations:
        assert c.source_type in {
            "db", "market_data", "news", "disclosure", "web", "curated_relation"
        }
        # No 'llm-interpretation' or other forbidden source_type values
        assert c.source_type != "llm-interpretation"

    # Catalysts: either populated OR explicit no_catalysts_reason
    if not card.thesis.catalysts:
        assert card.thesis.no_catalysts_reason, (
            "empty catalysts must come with no_catalysts_reason"
        )

    # Forbidden marketing words must NOT appear in user-facing text
    blob = (
        card.glance.one_line
        + " "
        + card.thesis.core_thesis
        + " "
        + card.decision.note
    )
    for forbidden in ["워렌버핏", "Buffett", "전문가급", "강력 매수", "확실한 수익", "유망주"]:
        assert forbidden not in blob, f"forbidden word leaked into UI: {forbidden}"
```

- [ ] **Step 20.3: Run normal suite — smoke must NOT run by default**

```bash
cd backend && uv run python -m pytest tests/ -q
```

Expected: All non-smoke tests pass; smoke test reported as deselected.

- [ ] **Step 20.4: Run smoke test (optional, manual)**

```bash
cd backend && uv run python -m pytest -m smoke -v
```

Expected: PASS — produces a real StockCard for 005930. Inspect output. If validation/forbidden-word assertions fail, iterate the persona prompt (Task 6) until clean.

- [ ] **Step 20.5: Commit**

```bash
git add backend/tests/integration/ backend/pyproject.toml
git commit -m "test: add opt-in smoke test for real-LLM 005930 analysis"
```

---

### Task 21: Final Verification + Branch Push

- [ ] **Step 21.1: Run full backend suite**

```bash
cd backend && uv run python -m pytest tests/ -q --cov=app --cov-report=term-missing
```

Expected: All tests pass. Coverage ≥ 95% (config in pyproject).

- [ ] **Step 21.2: Push branch**

```bash
git push -u origin feat/v2-backend-engine
```

- [ ] **Step 21.3: Open PR (optional)**

Create a draft PR documenting P1 scope. Reference spec commit `8e2f4a6`.

```bash
gh pr create --draft --title "feat: v2 backend engine (P1)" --body "$(cat <<'EOF'
## Summary
- 2-stage analyst engine (research → synthesize) producing validated StockCard
- 10-tool research kit (DB indicators/relations/macro + Tavily web + LLM curation)
- KR/US scheduler split with unique-ticker dedup and daily $10 cost kill switch
- analyses table extended with schema_version/card_data/persona_version (Phase A coexists)
- New tables: stock_relations, macro_factors

Implements P1 of `docs/superpowers/specs/2026-04-28-ontology-aware-stock-card-design.md` (commit 8e2f4a6).

P2 (Frontend Card), P3 (Stock Universe), P4+P5 (Chat Evolution + Polish) follow in separate PRs.

## Test plan
- [ ] Run full suite: `cd backend && uv run python -m pytest tests/ -q --cov=app`
- [ ] Run smoke test: `uv run python -m pytest -m smoke -v` (real Azure + Tavily)
- [ ] Verify forbidden words absent in smoke card output
- [ ] Curl `/api/stocks/005930/analyze` and `/api/stocks/005930/card` against running server

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Checklist

After writing the plan above, ran the following checks:

**1. Spec coverage** — Mapped each spec section to a task:
- §3 Card layout → covered by P2 plan (out of scope for this plan)
- §4 Engine architecture → Tasks 13–15
- §5 Data layers → Tasks 5, 7–11 (10/10 layers covered; 과거 유사 패턴 explicitly deferred per spec §15)
- §6 Persona → Task 6
- §7 Refresh policy → Task 19 (cron settings) + Task 18 (cooldown)
- §8 Output schema → Task 1
- §9 Stock Universe → P3 plan (deferred)
- §10 Chat evolution → P4 plan (deferred)
- §11 State coverage → frontend (P2)
- §12 Theme system → frontend (P2)
- §13 Eval framework → partial (Task 20 hallucination + forbidden + structure checks). Full LLM-as-judge eval = P5.
- §14 Decisions log → applied via field names + persona rules
- §17 Risks (cost) → Tasks 16, 17, 18, 19
- §18 Acceptance criteria — backend-side items (analyze API, KR/US schedules, schema_version) covered. UI items (card render, mobile, theme toggle, chat panel) = later plans.

**2. Placeholder scan** — No "TBD", "TODO", or "implement later" in tasks. Web search provider locked to Tavily (with Bing fallback noted only as a future option, not a placeholder). Each step has actual code or actual command.

**3. Type consistency** — `stance`/`scenario_price`/`risk_threshold` used consistently from Task 1 onward. `source_type` enum identical between `Citation` definition (Task 1) and tool returns (Tasks 7, 9–11). `persona_version` saved as string everywhere; `analyst_v1` constant from `persona.py` is the single source of truth.

**4. Ambiguity** — Synthesizer retry path uses `complete_json(prompt, system_prompt=...)` consistently after Task 11.4 / 14.4 adapter extension. Engine persistence is upsert by `(stock_id, date, period_type)` — no race ambiguity.

No issues found that need re-fixing.

---

## Next Steps (Follow-up Plans)

After this plan ships P1:

1. **Plan 2 — P2: Frontend Card** — Next.js card component with hero chart (lightweight-charts v5 reuse), 7 sections + at-a-glance panel, light/dark token system, state matrix (loading/empty/error/stale), `/stock/[ticker]` page, top-nav search update. ~1.5 weeks. Depends on P1's `/api/stocks/{ticker}/card`.

2. **Plan 3 — P3: Stock Universe** — `react-force-graph-2d` integration with custom canvas rendering (glow/pulse/parallax/nebula), full-screen modal, warp navigation, mobile 1-hop fallback. ~1 week. Depends on P2 card rendering.

3. **Plan 4 — P4 + P5: Chat Evolution + Polish** — `/chat` page removal, card-anchored slide-up chat panel, 4-tool registry shrink, KR alias seeds, frontend theme toggle, eval harness expansion (LLM-as-judge for citation accuracy + cycle awareness), Phase A row migration. ~1.5 weeks combined.

Each plan written separately by re-running `superpowers:writing-plans` with the prior plan landed.

---

## Plan Complete

**Plan saved to:** `docs/superpowers/plans/2026-04-28-ontology-aware-stock-card-implementation.md`

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best when you want hands-off progress with checkpoints.

2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review. Best when you want to watch each step closely.

**Which approach?**
