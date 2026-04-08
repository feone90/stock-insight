STOCKS = [
    {
        "ticker": "005930",
        "name": "삼성전자",
        "market": "KRX",
        "sector": "반도체",
        "current_price": 71500,
        "change": -1200,
        "change_percent": -1.65,
    },
    {
        "ticker": "TSLA",
        "name": "Tesla",
        "market": "NASDAQ",
        "sector": "전기차/에너지",
        "current_price": 248.42,
        "change": -8.57,
        "change_percent": -3.33,
    },
]


def search_stocks(query: str) -> list[dict]:
    q = query.lower()
    return [s for s in STOCKS if q in s["name"].lower() or q in s["ticker"].lower()]


def get_stock(ticker: str) -> dict | None:
    for s in STOCKS:
        if s["ticker"] == ticker:
            return s
    return None
