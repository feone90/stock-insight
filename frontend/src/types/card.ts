/**
 * Frontend mirror of backend `StockCard` Pydantic schema.
 *
 * Source of truth: `backend/app/schemas/card.py`. Keep in sync manually for now;
 * P5 polish introduces an automated generator (pydantic-to-ts / openapi-typescript).
 */

export type SourceType =
  | "db"
  | "market_data"
  | "news"
  | "disclosure"
  | "web"
  | "curated_relation";

export type InterpretationKind = "model_generated" | "rule_based";

export interface Citation {
  id: number;
  source_type: SourceType;
  label: string;
  url?: string | null;
  timestamp?: string | null; // ISO 8601
}

export interface Interpretation {
  kind: InterpretationKind;
  based_on: number[];
  rationale?: string | null;
}

export interface Claim {
  text: string;
  citations: number[];
  interpretation?: Interpretation | null;
}

export type Stance = "BUY" | "WATCH" | "REJECT";
export type EntryStage = "ENTER" | "WAIT" | "REJECT";
export type FinalGrade = "S" | "A" | "B" | "C" | "D";
export type GradeDelta = "up" | "down" | "same";
export type RelationType =
  | "peer"
  | "supply_upstream"
  | "supply_downstream"
  | "group"
  | "theme"
  | "macro"
  | "competitor"
  | "contract_supplier"
  | "contract_customer"
  | "complementary"
  | "regulatory_link";

export type SignalDirection = "positive" | "negative" | "inverse";
export type NewsImpact = "positive" | "negative" | "mixed" | "neutral";
export type CatalystDirection = "positive" | "negative" | "mixed";
export type ScenarioName = "BULL" | "BASE" | "BEAR";
export type MaStack = "정배열" | "역배열" | "혼조";
export type RefreshState = "fresh" | "stale" | "loading" | "error";

export interface GlanceVerdict {
  final_grade: FinalGrade;
  grade_delta?: GradeDelta | null;
  stance: Stance;
  entry_stage: EntryStage;
  one_line: string;
  citations: number[];
}

export interface TechMomentum {
  rsi_14: number | null;
  mfi_14: number | null;
  atr_pct: number | null;
  cmf_20: number | null;
  obv_ratio: number | null;
  ma_stack: MaStack | null;
  rvol_20: number | null;
  box_position: string | null;
  summary_line: string;
  citations: number[];
  interpretation?: Interpretation | null;
}

export interface Relation {
  target_ticker: string;
  target_name: string;
  relation_type: RelationType;
  strength: number;
  today_change_pct?: number | null;
  notes?: string | null;
  citation_ids: number[];
  // P1.6 v0+ — discovery + signal expressiveness.
  signal_direction?: SignalDirection;
  confidence?: number;
  source?: string;
  source_url?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  rationale?: string | null;
  // 10-K Item 1A LLM RAG (Codex I) 가 contract_customer rationale 안에서
  // 추출한 정량 매출 의존 % (0~100). 30%+ 면 frontend 가 lock-in risk 강조.
  customer_concentration_pct?: number | null;
  // 2026-05-15 — llm_knowledge source 가 채움. target_is_public=false 면
  // 비상장 (OpenAI/SpaceX 등) → 가격/차트 link 없이 read-only chip 표시.
  // business_importance 1-5 ★ 시각화.
  target_is_public?: boolean;
  business_importance?: number | null;
}

export interface RelationsSummary {
  one_line: string;
  relations: Relation[];
  citations: number[];
}

export interface NewsItem {
  title: string;
  source: string;
  url: string;
  published_at: string;
  impact: NewsImpact;
  summary: string;
  citation_id: number;
}

export interface MacroSensitivity {
  factor: string;
  beta: number;
  direction: "positive" | "negative" | "neutral";
}

export interface MacroContext {
  one_line: string;
  vix: number | null;
  fx_pairs: Record<string, number>;
  us_10y: number | null;
  sensitivities: MacroSensitivity[];
  upcoming_events: string[];
  citations: number[];
}

export interface Fundamentals {
  per?: number | null;
  pbr?: number | null;
  market_cap_krw?: number | null;
  dividend_yield?: number | null;
  per_5y_z?: number | null;
  source_label?: string | null;
  citations: number[];
}

// US-only — Finnhub free tier 다음 실적 발표 1건.
export interface Earnings {
  date: string;          // YYYY-MM-DD
  days_until: number;    // 카드 생성 시점 기준 D-N (음수면 과거)
  eps_estimate: number | null;
  revenue_estimate: number | null;
  hour: string | null;   // bmo / amc / dmh
}

// US-only — Finnhub analyst recommendation consensus 가장 최근 월.
export interface AnalystRating {
  month: string;
  buy: number;
  hold: number;
  sell: number;
  strong_buy: number;
  strong_sell: number;
}

// US-only — Finnhub 1년 목표주가 consensus (high/low/mean/median).
export interface PriceTarget {
  target_high: number | null;
  target_low: number | null;
  target_mean: number | null;
  target_median: number | null;
  n_analysts: number | null;
  last_updated: string | null;  // YYYY-MM-DD
}

// US-only — SEC Form 4 (임원 매매 신고) 최근 N일 요약.
// KR 종목은 null. 매수/매도 transaction code 분류는 follow-up (Form 4 XML 파싱).
export interface InsiderFiling {
  filing_date: string;
  accession: string;
  url: string | null;
}
export interface Insider {
  window_days: number;
  filing_count: number;
  recent: InsiderFiling[];
  as_of: string | null;
}

// KR-only — pykrx 수급(외국인/기관 5d 순매수 + 연속 일수).
// US 종목은 null. 가족 친화 카피는 frontend 책임 — 정량값만 raw 로 받음.
// 공매도(잔고/회전) 필드는 2026-05-14 사용자 결정으로 drop.
export interface Flow {
  foreign_net_5d_krw: number | null;
  inst_net_5d_krw: number | null;
  foreign_streak_days: number;
  inst_streak_days: number;
  as_of: string | null;
}

export interface Catalyst {
  when: string;
  event: string;
  impact_estimate: string;
  direction: CatalystDirection;
  citation_ids: number[];
}

export interface Scenario {
  name: ScenarioName;
  probability: number;
  scenario_price: number | null;
  scenario_change_pct: number | null;
  rationale: string;
}

export interface Thesis {
  core_thesis: string;
  supports: Claim[];
  opposes: Claim[];
  catalysts: Catalyst[];
  no_catalysts_reason?: string | null;
  scenarios: Scenario[];
  citations: number[];
}

export interface Decision {
  stance: Stance;
  sizing_note: string;
  support_price: number | null;
  risk_threshold: number | null;
  note: string;
  citations: number[];
  interpretation?: Interpretation | null;
}

export interface PoliticalSignalCard {
  posted_at: string;
  author: string;
  source: string;
  url: string | null;
  summary_ko: string;
  overall_sentiment: "bullish" | "bearish" | "neutral" | "mixed";
  macro_themes: string[];
  sentiment: "bullish" | "bearish" | "neutral";
  direction: "long" | "short" | "avoid";
  strength: "high" | "medium" | "low";
  confidence: number;
  expected_window: "minutes" | "hours" | "1-3days" | "1-2weeks";
  reasoning: string;
  sector_impact: string | null;
}

export interface StockCard {
  // Stock metadata
  ticker: string;
  name_ko: string;
  name_en: string;
  market: string;
  sector: string;
  tags: string[];
  price: number;
  change: number;
  change_pct: number;
  asof: string | null;

  // Analytical content
  glance: GlanceVerdict;
  thesis: Thesis;
  technical: TechMomentum;
  relations: RelationsSummary;
  news: NewsItem[];
  political_signals: PoliticalSignalCard[];
  macro: MacroContext;
  fundamentals: Fundamentals;
  flow?: Flow | null;                  // KR-only pykrx 수급+공매도.
  insider?: Insider | null;            // US-only SEC Form 4 임원 매매 신고.
  earnings?: Earnings | null;          // US-only Finnhub 다음 실적 발표 D-N.
  analyst_rating?: AnalystRating | null; // US-only Finnhub 분석가 의견 consensus.
  price_target?: PriceTarget | null;     // US-only Finnhub 분석가 1년 목표주가.
  decision: Decision;

  citations: Citation[];

  // Server metadata
  analysis_id: string;
  generated_at: string;
  persona_version: string;
  schema_version: string;
  refresh_state: RefreshState;

  // Per-layer freshness (3-way refresh split, 2026-05-14). Each refresh
  // button renders its own "마지막 갱신 N분 전" badge under itself —
  // generated_at is no longer the only timestamp shown.
  price_asof?: string | null;
  news_latest_at?: string | null;
}
