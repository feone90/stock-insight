/**
 * Market identification helpers.
 *
 * Stock.market 값 종류 (backend app.markets 기준):
 *   - KR: "KOSPI", "KOSDAQ", "KRX"
 *   - US: "NASDAQ", "NYSE", "US", "NMS", "NYQ", "AMEX", "NYSEARCA"
 *
 * 2026-05-18 — 옛 코드에서 `market === "KR"` 또는 `market === "KRX"`
 * 비교가 종종 보였음 → 둘 다 production 값과 안 맞아 KR 종목이 $ 로
 * 표시되던 버그. 항상 이 helper 사용.
 */

const KR_MARKETS = new Set(["KOSPI", "KOSDAQ", "KRX"]);
const US_MARKETS = new Set(["NASDAQ", "NYSE", "NYSEARCA", "US", "NMS", "NYQ", "AMEX"]);

export function isKRMarket(market: string | null | undefined): boolean {
  return market != null && KR_MARKETS.has(market);
}

export function isUSMarket(market: string | null | undefined): boolean {
  return market != null && US_MARKETS.has(market);
}

/** "₩" / "$" / "" — 화면 헤더의 가격 prefix. */
export function currencyMark(market: string | null | undefined): string {
  if (isKRMarket(market)) return "₩";
  if (isUSMarket(market)) return "$";
  return "";
}

/** "원" / "달러" — long-form, list/tooltip 등. */
export function currencyUnit(market: string | null | undefined): string {
  if (isKRMarket(market)) return "원";
  if (isUSMarket(market)) return "달러";
  return "";
}

/**
 * 장 개장 중인지 판단. 공휴일 무시 (정확한 캘린더 없이 시간 범위만).
 * KR: 평일 09:00-15:30 KST
 * US: 평일 09:30-16:00 America/New_York. 브라우저 Intl 시간대 변환으로
 *     서머타임은 자동 반영한다.
 *
 * 자동 가격 polling 이 장 외 시간엔 무의미 (가격 자체 안 변함) — yfinance/
 * pykrx 호출 절약.
 */
export function isMarketOpen(market: string | null | undefined, at: Date = new Date()): boolean {
  if (!market) return false;
  if (isKRMarket(market)) {
    const local = zonedMinuteOfWeek(at, "Asia/Seoul");
    return isWeekday(local.weekday) && local.minute >= 9 * 60 && local.minute <= 15 * 60 + 30;
  }
  if (isUSMarket(market)) {
    const local = zonedMinuteOfWeek(at, "America/New_York");
    return isWeekday(local.weekday) && local.minute >= 9 * 60 + 30 && local.minute <= 16 * 60;
  }
  return false;
}

function isWeekday(weekday: number): boolean {
  return weekday >= 1 && weekday <= 5;
}

function zonedMinuteOfWeek(at: Date, timeZone: string): { weekday: number; minute: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(at);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    weekday: WEEKDAY_INDEX[values.weekday ?? "Sun"] ?? 0,
    minute: Number(values.hour ?? 0) * 60 + Number(values.minute ?? 0),
  };
}

const WEEKDAY_INDEX: Record<string, number> = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
};
