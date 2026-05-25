"""외부 API에서 종목 정보를 조회하여 DB에 등록한다."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock


_NASDAQ_CODES = {"NMS", "NGM", "NCM", "NASDAQ", "NAS"}
_NYSE_CODES = {"NYQ", "NYSE", "NYS", "PCX", "BTS"}
_AMEX_CODES = {"ASE", "AMEX", "ASEMKT"}
_KRX_CODES = {"KSC", "KOE", "KRX", "KOSPI", "KOSDAQ"}


def _normalize_market(exchange: str, ticker_candidate: str = "") -> str:
    """yfinance exchange 코드를 정규화된 market 값으로 변환한다."""
    ex = exchange.upper()
    if ex in _KRX_CODES or ".KS" in ticker_candidate or ".KQ" in ticker_candidate:
        return "KRX"
    if ex in _NASDAQ_CODES or "NAS" in ex:
        return "NASDAQ"
    if ex in _NYSE_CODES or "NYS" in ex:
        return "NYSE"
    if ex in _AMEX_CODES:
        return "AMEX"
    return exchange or "OTHER"


def _lookup_yfinance(query: str) -> list[dict]:  # pragma: no cover
    """yfinance로 종목을 검색한다 (동기 호출)."""
    import yfinance as yf
    q = query.upper().strip()

    # 시도할 ticker 목록: 원본 + 한국 거래소 접미사
    candidates = [q]
    if q.isdigit():
        candidates.extend([f"{q}.KS", f"{q}.KQ"])

    for candidate in candidates:
        try:
            t = yf.Ticker(candidate)
            info = t.info or {}
            if not info.get("symbol") or not info.get("shortName"):
                continue
            exchange = (info.get("exchange") or "").upper()
            market = _normalize_market(exchange, candidate)
            ticker_clean = q if market == "KRX" else info["symbol"]
            return [{
                "ticker": ticker_clean,
                "name": info.get("shortName", info["symbol"]),
                "market": market,
                "sector": info.get("sector", ""),
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice") or 0,
            }]
        except Exception:
            continue
    return []


def _lookup_yfinance_search(query: str) -> list[dict]:  # pragma: no cover
    """Yahoo Finance search for company-name queries.

    `yf.Ticker(query).info` only works when `query` is already a ticker. This
    search path covers non-S&P and not-yet-seeded US names such as
    "Bloom Energy" -> BE.
    """
    import yfinance as yf

    try:
        search = yf.Search(query.strip(), max_results=10)
    except Exception:
        return []

    results: list[dict] = []
    seen: set[str] = set()
    for quote in getattr(search, "quotes", []) or []:
        if (quote.get("quoteType") or "").upper() != "EQUITY":
            continue
        symbol = (quote.get("symbol") or "").upper().strip()
        if not symbol or symbol in seen:
            continue
        exchange = (quote.get("exchange") or quote.get("exchDisp") or "").upper()
        market = _normalize_market(exchange, symbol)
        if market not in {"NASDAQ", "NYSE", "AMEX"}:
            continue
        seen.add(symbol)
        results.append({
            "ticker": symbol,
            "name": quote.get("longname") or quote.get("shortname") or symbol,
            "market": market,
            "sector": quote.get("sector") or quote.get("sectorDisp") or "",
            "current_price": quote.get("regularMarketPrice") or 0,
        })
    return results


def _lookup_fdr(query: str) -> list[dict]:  # pragma: no cover
    """FinanceDataReader로 한국 종목을 검색한다 (동기 호출)."""
    try:
        import FinanceDataReader as fdr
        listing = fdr.StockListing("KRX")
        # 이름 또는 코드로 검색
        matches = listing[
            listing["Name"].str.contains(query, case=False, na=False) |
            listing["Code"].str.contains(query.upper(), na=False)
        ].head(10)
        results = []
        for _, row in matches.iterrows():
            market = row.get("Market", "KRX")
            if market in ("KOSPI", "KOSDAQ"):
                market = "KRX"
            results.append({
                "ticker": row["Code"],
                "name": row["Name"],
                "market": market,
                "sector": row.get("Sector", "") or "",
                "current_price": float(row.get("Close", 0) or 0),
            })
        return results
    except Exception:
        return []


async def search_external(query: str) -> list[dict]:
    """외부 API에서 종목을 검색한다. KR(FDR) + US(yfinance) 동시 조회."""
    fdr_results, yf_results, yf_search_results = await asyncio.gather(
        asyncio.to_thread(_lookup_fdr, query),
        asyncio.to_thread(_lookup_yfinance, query),
        asyncio.to_thread(_lookup_yfinance_search, query),
        return_exceptions=True,
    )
    results = []
    seen: set[str] = set()
    if isinstance(fdr_results, list):
        for item in fdr_results:
            ticker = item.get("ticker")
            if ticker and ticker not in seen:
                results.append(item)
                seen.add(ticker)
    if isinstance(yf_results, list):
        for item in yf_results:
            ticker = item.get("ticker")
            if ticker and ticker not in seen:
                results.append(item)
                seen.add(ticker)
    if isinstance(yf_search_results, list):
        for item in yf_search_results:
            ticker = item.get("ticker")
            if ticker and ticker not in seen:
                results.append(item)
                seen.add(ticker)
    return results


async def register_stock(db: AsyncSession, ticker: str) -> Stock | None:
    """ticker로 외부 조회 후 DB에 등록한다. 이미 있으면 기존 반환."""
    existing = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = existing.scalar_one_or_none()
    if stock:
        return stock

    results = await asyncio.to_thread(_lookup_yfinance, ticker)
    if not results:
        results = await asyncio.to_thread(_lookup_fdr, ticker)
    if not results:
        return None

    info = results[0]
    stock = Stock(
        ticker=info["ticker"],
        name=info["name"],
        market=info["market"],
        sector=info.get("sector", ""),
        current_price=info.get("current_price", 0),
    )
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    return stock
