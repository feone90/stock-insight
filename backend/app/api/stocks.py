from fastapi import APIRouter, HTTPException

from app.mocks.stocks import search_stocks, get_stock
from app.mocks.prices import generate_prices
from app.mocks.analysis import get_stats
from app.mocks.favorites import is_favorite

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search")
def search(q: str = ""):
    if not q:
        return []
    return search_stocks(q)


@router.get("/{ticker}")
def stock_detail(ticker: str):
    stock = get_stock(ticker)
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    stats = get_stats(ticker)
    return {
        **stock,
        "is_favorite": is_favorite(ticker),
        "stats": stats,
    }


@router.get("/{ticker}/prices")
def stock_prices(ticker: str, days: int = 30):
    stock = get_stock(ticker)
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return generate_prices(ticker, days)
