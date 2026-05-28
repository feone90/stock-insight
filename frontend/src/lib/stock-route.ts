export function safeDecodeRouteParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function stockHref(ticker: string): string {
  return `/stock/${encodeURIComponent(ticker)}`;
}

export function isLikelyListedTicker(value: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9.-]{0,15}$/.test(value.trim());
}
