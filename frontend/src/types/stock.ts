export interface Stock {
  ticker: string;
  name: string;
  market: string;
  sector: string;
  current_price: number;
  change: number;
  change_percent: number;
  is_favorite?: boolean;
  stats?: StatsInfo;
}

export interface StatsInfo {
  market_cap: string;
  per: number;
  pbr: number;
  dividend_yield: number;
  high_52w: number;
  low_52w: number;
}

export interface PriceRecord {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface KeywordDetail {
  keyword: string;
  type: "bullish" | "bearish" | "neutral";
  detail: string;
  source: string;
  impact_level: "high" | "mid" | "low";
  duration: "short" | "mid" | "long";
}

export interface DailyKeyword {
  date: string;
  keyword: string;
  type: "bullish" | "bearish" | "neutral";
}

export interface Analysis {
  date: string;
  period_type: string;
  keywords: KeywordDetail[];
  daily_keywords: DailyKeyword[];
  summary: string;
  feedback: string;
}
