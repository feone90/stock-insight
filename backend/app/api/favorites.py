from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Favorite, Stock

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("")
async def list_favorites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Stock)
        .join(Favorite, Favorite.stock_id == Stock.id)
        .order_by(Favorite.created_at.desc())
    )
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


@router.post("/{ticker}")
async def add(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    existing = await db.execute(
        select(Favorite).where(Favorite.stock_id == stock.id)
    )
    if existing.scalar_one_or_none():
        return {"status": "already_exists", "ticker": ticker}

    db.add(Favorite(stock_id=stock.id))
    await db.commit()
    return {"status": "added", "ticker": ticker}


@router.delete("/{ticker}")
async def remove(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    fav_result = await db.execute(
        select(Favorite).where(Favorite.stock_id == stock.id)
    )
    fav = fav_result.scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()

    return {"status": "removed", "ticker": ticker}
