import random
from datetime import datetime, timedelta


def generate_prices(ticker: str, days: int = 30) -> list[dict]:
    base_prices = {
        "005930": 71500,
        "TSLA": 248.42,
    }
    base = base_prices.get(ticker, 100)
    prices = []
    current = base * 0.95
    today = datetime(2026, 4, 8)

    for i in range(days, 0, -1):
        date = today - timedelta(days=i)
        if date.weekday() >= 5:
            continue
        change_pct = random.uniform(-0.03, 0.03)
        open_price = round(current, 2)
        close_price = round(current * (1 + change_pct), 2)
        high_price = round(max(open_price, close_price) * (1 + random.uniform(0, 0.015)), 2)
        low_price = round(min(open_price, close_price) * (1 - random.uniform(0, 0.015)), 2)
        volume = random.randint(5000000, 30000000)

        prices.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
        })
        current = close_price

    return prices
