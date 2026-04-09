from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Favorite, PriceHistory, Stock
from app.models.financial import Financial

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search")
async def search(q: str = "", db: AsyncSession = Depends(get_db)):
    if not q:
        return []
    query = select(Stock).where(
        Stock.name.ilike(f"%{q}%") | Stock.ticker.ilike(f"%{q}%")
    )
    result = await db.execute(query)
    stocks = result.scalars().all()
    return [
        {
            "ticker": s.ticker,
            "name": s.name,
            "market": s.market,
            "sector": s.sector,
            "current_price": s.current_price,
            "change": s.change,
            "change_percent": s.change_percent,
        }
        for s in stocks
    ]


@router.get("/{ticker}")
async def stock_detail(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    fav_result = await db.execute(
        select(Favorite).where(Favorite.stock_id == stock.id)
    )
    is_fav = fav_result.scalar_one_or_none() is not None

    # financials 테이블에서 최신 재무지표 조회
    fin_result = await db.execute(
        select(Financial)
        .where(Financial.stock_id == stock.id)
        .order_by(Financial.created_at.desc())
        .limit(1)
    )
    fin = fin_result.scalar_one_or_none()

    stats = None
    if fin:
        # 52주 최고/최저를 price_history에서 계산
        from sqlalchemy import func as sql_func
        from datetime import date, timedelta
        year_ago = date.today() - timedelta(days=365)
        hl_result = await db.execute(
            select(
                sql_func.max(PriceHistory.high),
                sql_func.min(PriceHistory.low),
            ).where(
                PriceHistory.stock_id == stock.id,
                PriceHistory.date >= year_ago,
            )
        )
        high_52w, low_52w = hl_result.one()
        stats = {
            "market_cap": f"{fin.market_cap:,}" if fin.market_cap else "N/A",
            "per": round(fin.per, 1) if fin.per else 0,
            "pbr": round(fin.pbr, 1) if fin.pbr else 0,
            "dividend_yield": round(fin.dividend_yield, 1) if fin.dividend_yield else 0,
            "high_52w": high_52w or 0,
            "low_52w": low_52w or 0,
        }

    return {
        "ticker": stock.ticker,
        "name": stock.name,
        "market": stock.market,
        "sector": stock.sector,
        "current_price": stock.current_price,
        "change": stock.change,
        "change_percent": stock.change_percent,
        "is_favorite": is_fav,
        "stats": stats,
    }


@router.get("/{ticker}/prices")
async def stock_prices(ticker: str, days: int = 30, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    prices_result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.stock_id == stock.id)
        .order_by(PriceHistory.date.desc())
        .limit(days)
    )
    prices = prices_result.scalars().all()

    return [
        {
            "date": p.date.isoformat(),
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
        }
        for p in reversed(prices)
    ]
