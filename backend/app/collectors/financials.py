import asyncio
from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.markets import is_kr
from app.models import Stock
from app.models.financial import Financial


def _yf_suffixes_for_market(market: str | None) -> tuple[str, ...]:
    if market == "KOSPI":
        return (".KS",)
    if market == "KOSDAQ":
        return (".KQ",)
    if is_kr(market):
        return (".KS", ".KQ")
    return ("",)


def fetch_yfinance_financials(ticker: str, suffixes: tuple[str, ...]) -> dict:  # pragma: no cover
    """yfinance로 재무지표 조회. KR은 .KS/.KQ suffix 순차 시도."""
    import yfinance as yf

    for suffix in suffixes:
        symbol = f"{ticker}{suffix}"
        try:
            info = yf.Ticker(symbol).info
        except Exception:
            continue
        if info and (info.get("marketCap") or info.get("totalRevenue")):
            return info
    return {}


async def sync_financials(db: AsyncSession, stock: Stock) -> dict:
    """종목의 재무지표를 동기화한다. US/KR 공통 yfinance 경로."""
    period = f"{date.today().year}Q0"  # 최신 (TTM)

    try:
        suffixes = _yf_suffixes_for_market(stock.market)
        info = await asyncio.to_thread(fetch_yfinance_financials, stock.ticker, suffixes)
        if not info:
            return {"financials_synced": 0, "error": "재무 데이터 없음 (yfinance)"}

        roe = info.get("returnOnEquity")
        div_yield = info.get("dividendYield")

        values = {
            "stock_id": stock.id,
            "period": period,
            "period_type": "ttm",
            "revenue": int(info["totalRevenue"]) if info.get("totalRevenue") else None,
            "operating_profit": int(info["operatingIncome"]) if info.get("operatingIncome") else None,
            "net_income": int(info["netIncome"]) if info.get("netIncome") else None,
            "per": info.get("trailingPE"),
            "pbr": info.get("priceToBook"),
            "roe": round(roe * 100, 2) if roe else None,
            "dividend_yield": round(div_yield * 100, 2) if div_yield else None,
            "market_cap": info.get("marketCap"),
        }

        update_values = {k: v for k, v in values.items() if k not in ("stock_id", "period", "period_type")}

        stmt = insert(Financial).values(**values).on_conflict_do_update(
            constraint="uq_financial_stock_period",
            set_=update_values,
        )
        await db.execute(stmt)
        await db.commit()
        return {"financials_synced": 1}

    except Exception as e:
        return {"financials_synced": 0, "error": f"재무지표 동기화 실패: {e}"}
