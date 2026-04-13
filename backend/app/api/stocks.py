from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sql_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.favorites import _get_user_id
from app.collectors.stock_lookup import register_stock, search_external
from app.database import get_db
from app.dependencies import get_stock_or_404
from app.models import Favorite, PriceHistory, Stock
from app.models.disclosure import Disclosure
from app.models.financial import Financial
from app.models.news import News
from app.schemas.stock import (
    DisclosureResponse,
    NewsResponse,
    PriceResponse,
    StockDetailResponse,
    StockResponse,
)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search", response_model=list[StockResponse])
async def search(q: str = "", db: AsyncSession = Depends(get_db)):
    if not q:
        return []

    # 1. DB에서 먼저 검색
    query = select(Stock).where(
        Stock.name.ilike(f"%{q}%") | Stock.ticker.ilike(f"%{q}%")
    )
    result = await db.execute(query)
    db_stocks = result.scalars().all()
    db_tickers = {s.ticker for s in db_stocks}

    responses = [
        StockResponse(
            ticker=s.ticker, name=s.name, market=s.market, sector=s.sector,
            current_price=s.current_price, change=s.change, change_percent=s.change_percent,
        )
        for s in db_stocks
    ]

    # 2. DB 결과가 적으면 외부 API에서 추가 검색
    if len(responses) < 5:
        try:
            external = await search_external(q)
            for ext in external:
                if ext["ticker"] not in db_tickers:
                    responses.append(StockResponse(
                        ticker=ext["ticker"], name=ext["name"], market=ext["market"],
                        sector=ext.get("sector"), current_price=ext.get("current_price"),
                    ))
                    db_tickers.add(ext["ticker"])
        except Exception:
            pass  # 외부 검색 실패해도 DB 결과는 반환

    return responses


@router.post("/register/{ticker}", response_model=StockResponse)
async def register(ticker: str, db: AsyncSession = Depends(get_db)):
    """외부 API에서 종목 정보를 조회하여 DB에 등록한다."""
    stock = await register_stock(db, ticker)
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return StockResponse(
        ticker=stock.ticker, name=stock.name, market=stock.market, sector=stock.sector,
        current_price=stock.current_price, change=stock.change, change_percent=stock.change_percent,
    )


@router.get("/{ticker}", response_model=StockDetailResponse)
async def stock_detail(stock: Stock = Depends(get_stock_or_404), user_id: str = Depends(_get_user_id), db: AsyncSession = Depends(get_db)):
    fav_result = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.stock_id == stock.id)
    )
    is_fav = fav_result.scalar_one_or_none() is not None

    fin_result = await db.execute(
        select(Financial)
        .where(Financial.stock_id == stock.id)
        .order_by(Financial.created_at.desc())
        .limit(1)
    )
    fin = fin_result.scalar_one_or_none()

    stats = None
    if fin:
        year_ago = date_type.today() - timedelta(days=365)
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

    return StockDetailResponse(
        ticker=stock.ticker, name=stock.name, market=stock.market, sector=stock.sector,
        current_price=stock.current_price, change=stock.change, change_percent=stock.change_percent,
        is_favorite=is_fav, stats=stats,
    )


@router.get("/{ticker}/prices", response_model=list[PriceResponse])
async def stock_prices(days: int = 30, stock: Stock = Depends(get_stock_or_404), db: AsyncSession = Depends(get_db)):
    requested_start = date_type.today() - timedelta(days=days)

    prices_result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.stock_id == stock.id, PriceHistory.date >= requested_start)
        .order_by(PriceHistory.date.asc())
    )
    prices = prices_result.scalars().all()

    return [
        PriceResponse(
            date=p.date.isoformat(), open=p.open, high=p.high,
            low=p.low, close=p.close, volume=p.volume,
        )
        for p in prices
    ]


@router.get("/{ticker}/news", response_model=list[NewsResponse])
async def stock_news(limit: int = 50, stock: Stock = Depends(get_stock_or_404), db: AsyncSession = Depends(get_db)):
    news_result = await db.execute(
        select(News)
        .where(News.stock_id == stock.id)
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    news_list = news_result.scalars().all()

    return [
        NewsResponse(
            title=n.title, source=n.source, url=n.url,
            published_at=n.published_at.isoformat(),
        )
        for n in news_list
    ]


@router.get("/{ticker}/disclosures", response_model=list[DisclosureResponse])
async def stock_disclosures(limit: int = 30, stock: Stock = Depends(get_stock_or_404), db: AsyncSession = Depends(get_db)):
    disc_result = await db.execute(
        select(Disclosure)
        .where(Disclosure.stock_id == stock.id)
        .order_by(Disclosure.disclosed_at.desc())
        .limit(limit)
    )
    disc_list = disc_result.scalars().all()

    return [
        DisclosureResponse(
            title=d.title, disclosure_type=d.disclosure_type,
            disclosed_at=d.disclosed_at.isoformat(),
        )
        for d in disc_list
    ]
