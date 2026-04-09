from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Favorite, PriceHistory, Stock
from app.models.financial import Financial

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

STOCK_NOT_FOUND = "종목을 찾을 수 없습니다"


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
        raise HTTPException(status_code=404, detail=STOCK_NOT_FOUND)

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
        raise HTTPException(status_code=404, detail=STOCK_NOT_FOUND)

    from datetime import date as date_type, timedelta
    from sqlalchemy import func as sql_func

    # 요청 기간의 시작일
    requested_start = date_type.today() - timedelta(days=days)

    # DB에서 가장 오래된 데이터 확인
    oldest_result = await db.execute(
        select(sql_func.min(PriceHistory.date))
        .where(PriceHistory.stock_id == stock.id)
    )
    oldest_date = oldest_result.scalar()

    # 데이터가 없거나, 요청 기간보다 데이터가 부족하면 자동 수집
    if oldest_date is None or oldest_date > requested_start:
        from app.collectors.stock_price import sync_prices
        await sync_prices(db, stock, days=days)

    prices_result = await db.execute(
        select(PriceHistory)
        .where(
            PriceHistory.stock_id == stock.id,
            PriceHistory.date >= requested_start,
        )
        .order_by(PriceHistory.date.asc())
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
        for p in prices
    ]


@router.get("/{ticker}/news")
async def stock_news(ticker: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail=STOCK_NOT_FOUND)

    from app.models.news import News
    news_result = await db.execute(
        select(News)
        .where(News.stock_id == stock.id)
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    news_list = news_result.scalars().all()

    return [
        {
            "title": n.title,
            "source": n.source,
            "url": n.url,
            "published_at": n.published_at.isoformat(),
        }
        for n in news_list
    ]


@router.get("/{ticker}/disclosures")
async def stock_disclosures(ticker: str, limit: int = 30, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail=STOCK_NOT_FOUND)

    from app.models.disclosure import Disclosure
    disc_result = await db.execute(
        select(Disclosure)
        .where(Disclosure.stock_id == stock.id)
        .order_by(Disclosure.disclosed_at.desc())
        .limit(limit)
    )
    disc_list = disc_result.scalars().all()

    return [
        {
            "title": d.title,
            "disclosure_type": d.disclosure_type,
            "disclosed_at": d.disclosed_at.isoformat(),
        }
        for d in disc_list
    ]
