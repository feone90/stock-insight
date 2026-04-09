from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Favorite, Stock
from app.collectors.stock_price import sync_prices
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.disclosure import sync_disclosures
from app.collectors.exchange_rate import sync_exchange_rates

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/sync/stock/{ticker}")
async def sync_stock(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    prices_result = await sync_prices(db, stock)
    financials_result = await sync_financials(db, stock)
    news_result = await sync_news(db, stock)
    disclosures_result = await sync_disclosures(db, stock)

    errors = []
    for r in [prices_result, financials_result, news_result, disclosures_result]:
        if "error" in r:
            errors.append(r["error"])

    return {
        "status": "ok",
        "ticker": ticker,
        "synced": {
            "prices": prices_result.get("prices_synced", 0),
            "financials": financials_result.get("financials_synced", 0),
            "news": news_result.get("news_synced", 0),
            "disclosures": disclosures_result.get("disclosures_synced", 0),
        },
        "errors": errors,
    }


@router.post("/sync/global")
async def sync_global(db: AsyncSession = Depends(get_db)):
    rates_result = await sync_exchange_rates(db)

    errors = []
    if "error" in rates_result:
        errors.append(rates_result["error"])

    return {
        "status": "ok",
        "synced": {
            "exchange_rates": rates_result.get("exchange_rates_synced", 0),
        },
        "errors": errors,
    }


@router.post("/sync/all")
async def sync_all(db: AsyncSession = Depends(get_db)):
    fav_result = await db.execute(
        select(Stock).join(Favorite, Favorite.stock_id == Stock.id)
    )
    stocks = fav_result.scalars().all()

    total = {"prices": 0, "financials": 0, "news": 0, "disclosures": 0, "exchange_rates": 0}
    errors = []
    tickers_synced = []

    for stock in stocks:
        tickers_synced.append(stock.ticker)

        prices_result = await sync_prices(db, stock)
        financials_result = await sync_financials(db, stock)
        news_result = await sync_news(db, stock)
        disclosures_result = await sync_disclosures(db, stock)

        total["prices"] += prices_result.get("prices_synced", 0)
        total["financials"] += financials_result.get("financials_synced", 0)
        total["news"] += news_result.get("news_synced", 0)
        total["disclosures"] += disclosures_result.get("disclosures_synced", 0)

        for r in [prices_result, financials_result, news_result, disclosures_result]:
            if "error" in r:
                errors.append(f"[{stock.ticker}] {r['error']}")

    rates_result = await sync_exchange_rates(db)
    total["exchange_rates"] = rates_result.get("exchange_rates_synced", 0)
    if "error" in rates_result:
        errors.append(rates_result["error"])

    return {
        "status": "ok",
        "stocks_synced": tickers_synced,
        "global_synced": True,
        "total_synced": total,
        "errors": errors,
    }
