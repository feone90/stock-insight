"""외부 API에서 종목 정보를 조회하여 DB에 등록한다."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock


def _lookup_yfinance(query: str) -> list[dict]:  # pragma: no cover
    """yfinance로 종목을 검색한다 (동기 호출)."""
    import yfinance as yf
    results = []
    # 직접 ticker로 시도
    t = yf.Ticker(query.upper())
    info = t.info or {}
    if info.get("symbol") and info.get("shortName"):
        exchange = info.get("exchange", "")
        market = "NASDAQ" if "NAS" in exchange.upper() else "NYSE" if "NYS" in exchange.upper() else exchange
        results.append({
            "ticker": info["symbol"],
            "name": info.get("shortName", info["symbol"]),
            "market": market,
            "sector": info.get("sector", ""),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice") or 0,
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
    fdr_results, yf_results = await asyncio.gather(
        asyncio.to_thread(_lookup_fdr, query),
        asyncio.to_thread(_lookup_yfinance, query),
        return_exceptions=True,
    )
    results = []
    if isinstance(fdr_results, list):
        results.extend(fdr_results)
    if isinstance(yf_results, list):
        results.extend(yf_results)
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
