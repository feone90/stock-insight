import asyncio
from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Stock
from app.models.financial import Financial


def fetch_us_financials(ticker: str) -> dict:
    """yfinance로 US 재무지표 조회."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    return t.info


async def sync_financials(db: AsyncSession, stock: Stock) -> dict:
    """종목의 재무지표를 동기화한다."""
    period = f"{date.today().year}Q0"  # 최신 (TTM)

    try:
        if stock.market in ("NYSE", "NASDAQ"):
            info = await asyncio.to_thread(fetch_us_financials, stock.ticker)
            if not info:
                return {"financials_synced": 0, "error": "재무 데이터 없음"}

            values = {
                "stock_id": stock.id,
                "period": period,
                "period_type": "ttm",
                "revenue": int(info.get("totalRevenue", 0)) if info.get("totalRevenue") else None,
                "operating_profit": int(info.get("operatingIncome", 0)) if info.get("operatingIncome") else None,
                "net_income": int(info.get("netIncome", 0)) if info.get("netIncome") else None,
                "per": info.get("trailingPE"),
                "pbr": info.get("priceToBook"),
                "roe": round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else None,
                "dividend_yield": round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else None,
                "market_cap": info.get("marketCap"),
            }

            update_values = {k: v for k, v in values.items() if k not in ("stock_id", "period", "period_type")}

            stmt = insert(Financial).values(**values).on_conflict_do_update(
                constraint="uq_financial_stock_period",
                set_=update_values,
            )
            await db.execute(stmt)
        else:
            # KR: DART API — dart_code 필요
            if not stock.dart_code or not settings.dart_api_key:
                return {"financials_synced": 0, "error": "DART API 키 또는 기업코드 미설정"}
            return {"financials_synced": 0, "error": "KR 재무지표 DART 파싱 미구현"}

        await db.commit()
        return {"financials_synced": 1}

    except Exception as e:
        return {"financials_synced": 0, "error": f"재무지표 동기화 실패: {e}"}
