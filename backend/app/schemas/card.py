"""StockCard Pydantic schema — output of the v2 analyst engine.

Citation = data source ONLY. LLM interpretation lives in `Interpretation`,
attached to claims via `Claim.interpretation`. Don't conflate.

Field renames vs early drafts (do not regress):
- strategy → stance
- target_price → scenario_price
- target_change_pct → scenario_change_pct
- stop_loss → risk_threshold
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SourceType = Literal[
    "db",
    "market_data",
    "news",
    "disclosure",
    "web",
    "curated_relation",
]
InterpretationKind = Literal["model_generated", "rule_based"]

_RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*[~–—]\s*(\d{4}-\d{2}-\d{2})")
_SINGLE_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class Citation(BaseModel):
    id: int
    source_type: SourceType
    label: str
    url: str | None = None
    timestamp: datetime | None = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(cls, v):
        # LLM occasionally emits non-ISO strings (date ranges, embedded labels,
        # mojibake). Recover an end-date when a range is present, a single date
        # when one is embedded; fall back to null otherwise.
        if v is None or isinstance(v, datetime):
            return v
        if not isinstance(v, str):
            return None
        s = v.strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
        m = _RANGE_RE.search(s)
        if m:
            try:
                return datetime.fromisoformat(m.group(2))
            except ValueError:
                return None
        m = _SINGLE_DATE_RE.search(s)
        if m:
            try:
                return datetime.fromisoformat(m.group(0))
            except ValueError:
                return None
        return None


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
        "peer", "supply_upstream", "supply_downstream", "group", "theme", "macro",
        "competitor", "contract_supplier", "contract_customer",
        "complementary", "regulatory_link",
    ]
    strength: float = Field(..., ge=0, le=1)
    today_change_pct: float | None = None
    notes: str | None = None
    citation_ids: list[int]

    # P1.6 v0+ — discovery + signal expressiveness
    signal_direction: Literal["positive", "negative", "inverse"] = "positive"
    confidence: float = Field(default=0.5, ge=0, le=1)
    source: str = "curated_relation"  # sector_match / sec_8k / news / dart_contract / ...
    source_url: str | None = None
    valid_from: str | None = None  # ISO date
    valid_until: str | None = None
    # LLM 추출 시 prompt 가 요구한 "근거 한 줄" — 왜 이 관계로 분류했는지.
    # sector_match 같은 rule 기반 source 에는 비어있을 수 있음.
    rationale: str | None = None


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


class PoliticalSignalCard(BaseModel):
    """카드의 뉴스/이슈 섹션에 별도 highlight되는 정치 발언. 미래 자동매매
    trigger row의 read-only view. ticker별로 영향 metadata 포함."""

    posted_at: datetime
    author: str = "realDonaldTrump"
    source: str = "truth_social"
    url: str | None = None
    summary_ko: str
    overall_sentiment: Literal["bullish", "bearish", "neutral", "mixed"]
    macro_themes: list[str] = []

    # 이 ticker에 매핑된 분석 결과 (PoliticalSignalTicker 1 row)
    sentiment: Literal["bullish", "bearish", "neutral"]
    direction: Literal["long", "short", "avoid"]
    strength: Literal["high", "medium", "low"]
    confidence: float
    expected_window: Literal["minutes", "hours", "1-3days", "1-2weeks"]
    reasoning: str
    sector_impact: str | None = None


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
    political_signals: list[PoliticalSignalCard] = []
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
    political_signals: list[PoliticalSignalCard] = []
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

    @model_validator(mode="after")
    def _strip_dangling_citations(self) -> "AnalystOutput":
        # spec §6 originally said "LLM cites non-existent citation ID → retry"
        # but empirically the LLM hallucinates dangling citations even with
        # explicit retry prompts, especially when `interp_citations` is
        # naturally empty (e.g. stocks where fundamentals + news both
        # short on hard-cite-worthy data). Throwing a ValueError tanks the
        # whole analyze pass and leaves the user with no v2 card at all,
        # which is worse than showing a card with one missing footnote.
        # We strip the unknown ids, log them, and let the card render.
        valid_ids = {c.id for c in self.interp_citations}

        def _filter(ids: list[int], where: str) -> list[int]:
            bad = [i for i in ids if i not in valid_ids]
            if bad:
                import logging
                logging.getLogger(__name__).warning(
                    "dropping dangling citation ids %s from %s (pool=%s)",
                    bad, where, sorted(valid_ids),
                )
            return [i for i in ids if i in valid_ids]

        self.glance.citations = _filter(self.glance.citations, "glance")
        self.thesis.citations = _filter(self.thesis.citations, "thesis")
        self.relations_narrative.citations = _filter(
            self.relations_narrative.citations, "relations_narrative"
        )
        self.decision.citations = _filter(self.decision.citations, "decision")
        for i, claim in enumerate(self.thesis.supports):
            claim.citations = _filter(claim.citations, f"thesis.supports[{i}]")
            if claim.interpretation:
                claim.interpretation.based_on = _filter(
                    claim.interpretation.based_on,
                    f"thesis.supports[{i}].interpretation",
                )
        for i, claim in enumerate(self.thesis.opposes):
            claim.citations = _filter(claim.citations, f"thesis.opposes[{i}]")
            if claim.interpretation:
                claim.interpretation.based_on = _filter(
                    claim.interpretation.based_on,
                    f"thesis.opposes[{i}].interpretation",
                )
        for i, cat in enumerate(self.thesis.catalysts):
            cat.citation_ids = _filter(cat.citation_ids, f"thesis.catalysts[{i}]")
        if self.decision.interpretation:
            self.decision.interpretation.based_on = _filter(
                self.decision.interpretation.based_on, "decision.interpretation"
            )
        return self
