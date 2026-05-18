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
    # 표시용 모델 — 카드 응답에 직렬화됨. customer_concentration_pct 는
    # 10-K Item 1A LLM RAG (Codex I) 가 contract_customer rationale 안에서
    # "X accounted for 25% of revenue" 같은 정량 명시를 추출한 결과.
    # None 이면 frontend 가 일반 contract_customer row 로 표시.
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

    # Codex I — 10-K Item 1A 에 "X accounted for 25% of revenue" 같은 정량
    # 매출 의존 표현이 있을 때 contract_customer relation 에 박힌다. 30%+
    # 면 frontend 에서 risk badge 강조 (lock-in risk).
    customer_concentration_pct: float | None = Field(default=None, ge=0, le=100)

    # 2026-05-15 — LLM knowledge 기반 관계 표현력 확장.
    # `target_is_public=False` 면 비상장 entity (OpenAI, SpaceX 등). frontend
    # 가 가격/차트 link 없이 read-only chip 으로 표시.
    target_is_public: bool = True
    # 1 (주변) ~ 5 (매수 결정 핵심). knowledge_relations 가 채움; 다른 source
    # 는 None. frontend 가 ★ 1-5 시각화에 사용.
    business_importance: int | None = Field(default=None, ge=1, le=5)


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
    # 데이터 출처 사용자 표시용. 예: "DART · 사업보고서 (2023A)",
    # "yfinance · TTM (2026Q0)", "yfinance · 시총만 (DART 미공개)",
    # "시총만 — 재무 미수집 (분석 시작 전)". None이면 라벨 숨김.
    source_label: str | None = None
    citations: list[int] = []


class Flow(BaseModel):
    """KR 종목 — 외국인/기관 수급 (5일 누적 순매수 + 연속 일수).

    pykrx 보강(2026-05-14, Codex 시니어 트레이더 리뷰 권고). yfinance / dartlab
    이 못 채우는 영역. US 종목은 항상 None.

    공매도 잔고/회전은 2026-05-14 사용자 결정으로 drop — 가족 비전공자 retail
    의사결정에 nuanced + noise > signal.

    카드 노출 시 가족 친화 카피로 변환 — feedback_card_user_facing_copy 메모
    참조. 예: foreign_net_5d_krw=+120억 → "외국인이 최근 5일 동안 120억원
    순매수 (사들이고 있음)".
    """
    foreign_net_5d_krw: int | None = None    # 외국인 5거래일 순매수 (원)
    inst_net_5d_krw: int | None = None       # 기관 5거래일 순매수 (원)
    foreign_streak_days: int = 0             # +N 연속 매수 / -N 연속 매도
    inst_streak_days: int = 0
    as_of: str | None = None                 # 최근 거래일 (YYYY-MM-DD)


class Earnings(BaseModel):
    """US 종목 — Finnhub free tier earnings calendar 다음 발표 1건.

    매수/매도 판단 시점 결정에 핵심. 카드 노출 시 "다음 실적 발표 D-N (1주일 뒤)"
    가족 친화 카피로 frontend 변환.
    """
    date: str                       # YYYY-MM-DD
    days_until: int = 0             # 카드 생성 시점 기준 D-N (0 이면 오늘)
    eps_estimate: float | None = None
    revenue_estimate: int | None = None
    hour: str | None = None         # bmo / amc / dmh


class AnalystRating(BaseModel):
    """US 종목 — Finnhub analyst recommendation consensus 가장 최신 월.

    카피 가이드: "전문가 12명 의견: 매수 8 / 보유 3 / 매도 1".
    """
    month: str                      # YYYY-MM
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_buy: int = 0
    strong_sell: int = 0

    @property
    def total(self) -> int:
        return self.buy + self.hold + self.sell + self.strong_buy + self.strong_sell


class PriceTarget(BaseModel):
    """US 종목 — 분석가 1년 목표주가 consensus.

    카피 가이드: "전문가 N명 1년 후 평균 X달러 — 현재가 대비 +Y%". 가족
    친화 frontend 변환. high/low 는 range 표시 ("180~220달러 사이 의견 갈림").
    """
    target_high: float | None = None
    target_low: float | None = None
    target_mean: float | None = None
    target_median: float | None = None
    n_analysts: int | None = None
    last_updated: str | None = None    # YYYY-MM-DD


class InsiderFiling(BaseModel):
    filing_date: str
    accession: str
    url: str | None = None


class Insider(BaseModel):
    """US 종목 — SEC Form 4 (임원 매매 신고) 요약.

    Codex 권고(2026-05-14): "insider buying/selling and institutional position
    changes are table-stakes context, especially for small/mid caps".

    카피 가이드: "최근 30일 임원 매매 신고 N건 — 자세히 보기" 식으로 frontend
    에서 풀어 표현. KR 종목은 항상 None (KR 대량보유공시 5% 별도 collector
    필요 — follow-up).

    transaction code 별 매수/매도 분류는 Form 4 XML 파싱 추가 작업으로 별도
    sub-phase.
    """
    window_days: int = 30
    filing_count: int = 0
    recent: list[InsiderFiling] = []
    as_of: str | None = None


class PriceMoveCause(BaseModel):
    """최근 가격 움직임의 원인 후보. 시니어 분석가가 본 "왜 떨어졌나" 한 줄.

    2026-05-19 추가 — 사용자가 "한미반도체가 며칠 떨어지는데 왜 안 보이냐"
    피드백. evidence_kind 와 evidence_date 로 *어떤 자료* 가 근거인지 명확.

    confidence='low' + evidence_kind='valuation' 같은 *fundamental* origin 도
    OK (단순 밸류 부담 같은 추정).
    """
    text: str  # "HBM 경쟁자 출현 우려" 같은 한 줄 (가족 친화)
    confidence: Literal["high", "medium", "low"]
    evidence_kind: Literal[
        "news",        # raw 본문 인용 — 가장 확실
        "disclosure",  # 공시 (사업보고서, 8-K 등)
        "political",   # 정치 시그널 (트럼프 truth_social 등)
        "flow",        # 수급 (외국인/기관)
        "valuation",   # 밸류에이션 부담 (PER/PBR 정량 근거)
        "peer_move",   # 동종업계 동반 움직임
        "knowledge",   # 2026-05-19 — LLM 도메인 지식. 본문에 없지만 시니어
                       # 분석가가 *원인의 원인* 알 때 (예: 실적 발표 내용).
                       # 반드시 knowledge_cutoff_risk + confidence ≤ 0.6.
    ]
    evidence_date: str | None = None  # YYYY-MM-DD
    evidence_quote: str | None = None  # 본문 인용 (paraphrase 거부)
    # 2026-05-19 — evidence_kind="knowledge" 일 때 명시. LLM training cutoff
    # 이후 변경 가능성 — frontend 가 "추정" badge 추가 강조.
    knowledge_cutoff_risk: Literal["high", "low"] | None = None
    citation_id: int | None = None


class RecentPriceMove(BaseModel):
    """카드 헤더 아래 노출 — "최근 N거래일 -X% — 왜?" 답 layer.

    Deterministic 정량 (수익률 / 급락일) + 그 기간 evidence 후보 + LLM
    narrative (Beyond Meat 류 환상 재발 방지 — evidence 부족 시 unknown_or_
    unconfirmed 명시).
    """
    return_5d_pct: float | None = None
    return_14d_pct: float | None = None
    return_30d_pct: float | None = None
    # 대표 윈도우 — 가장 큰 폭 움직임 기준 선택. UI 의 메인 표시.
    primary_window: Literal["5d", "14d", "30d"] = "5d"
    biggest_move_date: str | None = None  # YYYY-MM-DD
    biggest_move_pct: float | None = None  # 단일 일 최대 변동 폭
    one_line: str  # "최근 5거래일 -8.3% — 급락" 식 가족 친화 한 줄
    causes: list[PriceMoveCause] = []
    # 확인된 직접 원인 부족할 때 명시 (예: "단기 수급/밸류에이션 조정으로
    # 추정 — 명시 catalyst 없음"). 환상 만들지 않게 사용자에게 *정직하게* 노출.
    unknown_or_unconfirmed: str | None = None


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
    flow: Flow | None = None              # KR-only: 외국인/기관 수급 + 공매도.
    insider: Insider | None = None        # US-only: SEC Form 4 최근 30일 요약.
    earnings: Earnings | None = None      # US-only: Finnhub 다음 실적 발표 D-N.
    analyst_rating: AnalystRating | None = None  # US-only: Finnhub 매수/보유/매도.
    price_target: PriceTarget | None = None  # US-only: Finnhub 1년 목표주가.
    # 2026-05-19 — 헤더 가격 바로 아래 "최근 N거래일 -X% 왜?" 답 layer.
    recent_price_move: "RecentPriceMove | None" = None
    decision: Decision

    citations: list[Citation] = []

    # Server-controlled metadata.
    analysis_id: str
    generated_at: datetime
    persona_version: str
    schema_version: str = "v1"
    refresh_state: Literal["fresh", "stale", "loading", "error"] = "fresh"

    # Per-layer freshness (3-way refresh split, 2026-05-14). Each data layer
    # decays at a different rate — price intraday, news hourly, AI 의견 only when
    # thesis changes — so the card surfaces a separate "마지막 갱신" timestamp
    # under each refresh button instead of one global generated_at.
    price_asof: datetime | None = None
    news_latest_at: datetime | None = None


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
    flow: Flow | None = None              # KR-only (pykrx 수급 + 공매도)
    insider: Insider | None = None        # US-only (SEC Form 4 30d)
    earnings: Earnings | None = None      # US-only (Finnhub 다음 발표)
    analyst_rating: AnalystRating | None = None  # US-only (Finnhub consensus)
    price_target: PriceTarget | None = None  # US-only (Finnhub 1년 목표주가)
    news: list[NewsItem] = []
    political_signals: list[PoliticalSignalCard] = []
    relations_data: list[Relation] = []
    recent_price_move: "RecentPriceMove | None" = None
    data_citations: list[Citation] = []

    # Per-layer freshness — surfaced to the card so each refresh button can
    # render its own "마지막 갱신: N분 전" badge. compose() pipes these into
    # StockCard.{price_asof,news_latest_at}. None means we couldn't determine
    # (no rows in PriceHistory/News yet).
    price_asof: datetime | None = None
    news_latest_at: datetime | None = None


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
    def _log_unresolved_citations(self) -> "AnalystOutput":
        # citation resolution moved to engine.compose so we can distinguish
        # three cases that the schema layer alone can't:
        #   (a) id ∈ interp_citations pool — register OK, compose shifts +K
        #   (b) 1 ≤ id ≤ K — LLM borrowed a data_citations id directly,
        #       compose keeps as-is. We *want* this — Naver/SEC/DART data
        #       gets footnoted without LLM re-registering.
        #   (c) id 어디에도 없음 — truly dangling, compose drops + logs.
        # The schema validator only sees (a) vs not-(a); stripping not-(a)
        # tanks both (b) and (c), leaving cards with empty footnotes even
        # when the LLM was actually trying to reference real data.
        valid_ids = {c.id for c in self.interp_citations}
        seen_unresolved: set[int] = set()
        for ids in (
            self.glance.citations,
            self.thesis.citations,
            self.relations_narrative.citations,
            self.decision.citations,
        ):
            for cid in ids:
                if cid not in valid_ids:
                    seen_unresolved.add(cid)
        if seen_unresolved:
            import logging
            logging.getLogger(__name__).info(
                "AnalystOutput has %d citation id(s) outside interp_citations pool — engine.compose will resolve against data pool",
                len(seen_unresolved),
            )
        return self
