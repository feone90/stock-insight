from fastapi import APIRouter

from app.mocks.favorites import get_favorites, add_favorite, remove_favorite
from app.mocks.stocks import get_stock

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("")
def list_favorites():
    tickers = get_favorites()
    stocks = []
    for ticker in tickers:
        stock = get_stock(ticker)
        if stock:
            stocks.append(stock)
    return stocks


@router.post("/{ticker}")
def add(ticker: str):
    add_favorite(ticker)
    return {"status": "added", "ticker": ticker}


@router.delete("/{ticker}")
def remove(ticker: str):
    remove_favorite(ticker)
    return {"status": "removed", "ticker": ticker}
