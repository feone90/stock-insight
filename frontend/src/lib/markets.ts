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

/**
 * 장 개장 중인지 대략 판단. 공휴일 무시 (정확한 캘린더 없이 시간 범위만).
 * KR: 평일 09:00-15:30 KST
 * US: 평일 22:30-05:00 KST (서머타임 ~1시간 차이 무시 — 대략 범위로 충분)
 *
 * 자동 가격 polling 이 장 외 시간엔 무의미 (가격 자체 안 변함) — yfinance/
 * pykrx 호출 절약.
 */
export function isMarketOpen(market: string | null | undefined): boolean {
  if (!market) return false;
  const now = new Date();
  const day = now.getUTCDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;
  const kstMin =
    ((now.getUTCHours() + 9) % 24) * 60 + now.getUTCMinutes();
  if (isKRMarket(market)) {
    return kstMin >= 9 * 60 && kstMin <= 15 * 60 + 30; // 09:00 ~ 15:30
  }
  if (isUSMarket(market)) {
    // 22:30 ~ 05:00 KST (자정 wrap). 서머타임 영향 ±1시간 무시.
    return kstMin >= 22 * 60 + 30 || kstMin <= 5 * 60;
  }
  return false;
}
