/**
 * Market identification helpers.
 *
 * Stock.market 값 종류 (backend app.markets 기준):
 *   - KR: "KOSPI", "KOSDAQ"
 *   - US: "NASDAQ", "NYSE", "US", "NYSEARCA"
 *
 * 2026-05-18 — 옛 코드에서 `market === "KR"` 또는 `market === "KRX"`
 * 비교가 종종 보였음 → 둘 다 production 값과 안 맞아 KR 종목이 $ 로
 * 표시되던 버그. 항상 이 helper 사용.
 */

const KR_MARKETS = new Set(["KOSPI", "KOSDAQ"]);
const US_MARKETS = new Set(["NASDAQ", "NYSE", "NYSEARCA", "US", "AMEX"]);

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
