from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_stock_or_404
from app.models import Favorite, Stock
from app.schemas.stock import FavoriteActionResponse, StockResponse

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("", response_model=list[StockResponse])
async def list_favorites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Stock)
        .join(Favorite, Favorite.stock_id == Stock.id)
        .order_by(Favorite.created_at.desc())
    )
    stocks = result.scalars().all()
    return [
        StockResponse(
            ticker=s.ticker, name=s.name, market=s.market, sector=s.sector,
            current_price=s.current_price, change=s.change, change_percent=s.change_percent,
        )
        for s in stocks
    ]


@router.post("/{ticker}", response_model=FavoriteActionResponse)
async def add(stock: Stock = Depends(get_stock_or_404), db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(Favorite).where(Favorite.stock_id == stock.id)
    )
    if existing.scalar_one_or_none():
        return FavoriteActionResponse(status="already_exists", ticker=stock.ticker)

    db.add(Favorite(stock_id=stock.id))
    await db.commit()
    return FavoriteActionResponse(status="added", ticker=stock.ticker)


@router.delete("/{ticker}", response_model=FavoriteActionResponse)
async def remove(stock: Stock = Depends(get_stock_or_404), db: AsyncSession = Depends(get_db)):
    fav_result = await db.execute(
        select(Favorite).where(Favorite.stock_id == stock.id)
    )
    fav = fav_result.scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()

    return FavoriteActionResponse(status="removed", ticker=stock.ticker)
