from fastapi import APIRouter, Depends
from sqlalchemy import func as sql_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.exchange_rate import ExchangeRate
from app.schemas.stock import ExchangeRateResponse

router = APIRouter(prefix="/api/exchange-rates", tags=["exchange-rates"])


@router.get("/latest", response_model=list[ExchangeRateResponse])
async def latest_rates(db: AsyncSession = Depends(get_db)):
    max_date_result = await db.execute(select(sql_func.max(ExchangeRate.date)))
    max_date = max_date_result.scalar()
    if not max_date:
        return []

    result = await db.execute(
        select(ExchangeRate).where(ExchangeRate.date == max_date)
    )
    rates = result.scalars().all()

    return [
        ExchangeRateResponse(
            date=r.date.isoformat(), currency_pair=r.currency_pair, rate=r.rate,
        )
        for r in rates
    ]
