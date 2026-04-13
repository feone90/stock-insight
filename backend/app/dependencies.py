"""공유 FastAPI 의존성."""

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Stock

STOCK_NOT_FOUND = "종목을 찾을 수 없습니다"


async def get_stock_or_404(ticker: str, db: AsyncSession = Depends(get_db)) -> Stock:
    """ticker로 종목을 조회한다. 없으면 404."""
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail=STOCK_NOT_FOUND)
    return stock
