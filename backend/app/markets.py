"""Centralized market code sets.

yfinance/FDR/SEC return varying exchange labels; collectors and routing
logic across the app must agree on which buckets are "KR" vs "US". Keeping
the canonical list here prevents drift (e.g. NEWS routed to Naver because
a US stock was tagged "NMS" instead of "NASDAQ").
"""

KR_MARKETS: frozenset[str] = frozenset({"KOSPI", "KOSDAQ", "KRX"})
US_MARKETS: frozenset[str] = frozenset({"NASDAQ", "NYSE", "US", "NMS", "NYQ", "AMEX"})


def is_kr(market: str | None) -> bool:
    return market in KR_MARKETS


def is_us(market: str | None) -> bool:
    return market in US_MARKETS
