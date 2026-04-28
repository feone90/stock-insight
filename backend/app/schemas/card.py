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
    per: float | None = None
    pbr: float | None = None
    market_cap_krw: float | None = None
    dividend_yield: float | None = None
    per_5y_z: float | None = None
    citations: list[int] = []


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
    # Stock metadata — server-injected from DB (LLM doesn't produce these).
    ticker: str
    name_ko: str = ""
    name_en: str = ""
    market: str = ""
    sector: str = ""
    tags: list[str] = []

    price: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    asof: datetime | None = None

    # Analytical content — LLM produces these.
    glance: GlanceVerdict
    thesis: Thesis
    technical: TechMomentum
    relations: RelationsSummary
    news: list[NewsItem] = []
    macro: MacroContext
    fundamentals: Fundamentals
    decision: Decision

    citations: list[Citation] = []

    # Server-controlled metadata.
    analysis_id: str
    generated_at: datetime
    persona_version: str
    schema_version: str = "v1"
    refresh_state: Literal["fresh", "stale", "loading", "error"] = "fresh"


# === Layered output (data vs analyst) — composed into StockCard at engine ===


class DataLayer(BaseModel):
    """Server-produced sections. No LLM judgment, only data plumbing.

    Each section may be `None` if its sub-fetch failed (graceful degrade);
    `engine.compose` substitutes a stub so the final StockCard contract holds.
    Citation IDs in nested fields reference `data_citations` (1..K).
    """
    technical: TechMomentum | None = None
    macro: MacroContext | None = None
    fundamentals: Fundamentals | None = None
    news: list[NewsItem] = []
    relations_data: list[Relation] = []
    data_citations: list[Citation] = []


class RelationsNarrative(BaseModel):
    """Analyst commentary that overlays `DataLayer.relations_data`."""
    one_line: str
    notes_by_target: dict[str, str] = {}
    citations: list[int] = []


class AnalystOutput(BaseModel):
    """The 4 LLM-produced judgment fields. No data echoing.

    Citation IDs in nested fields reference `interp_citations` (1..M),
    which `engine.compose` re-numbers to K+1..K+M when merging with
    `DataLayer.data_citations`.
    """
    glance: GlanceVerdict
    thesis: Thesis
    relations_narrative: RelationsNarrative
    decision: Decision
    interp_citations: list[Citation] = []
