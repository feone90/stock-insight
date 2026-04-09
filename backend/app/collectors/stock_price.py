import asyncio
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceHistory, Stock


def fetch_us_prices(ticker: str, start: str) -> pd.DataFrame:
    """yfinance로 US 주가 조회 (동기 함수)."""
    import yfinance as yf
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
    return df


def fetch_kr_prices(ticker: str, start: str) -> pd.DataFrame:
    """FinanceDataReader로 KR 주가 조회 (동기 함수)."""
    import FinanceDataReader as fdr
    df = fdr.DataReader(ticker, start)
    return df


async def sync_prices(db: AsyncSession, stock: Stock) -> dict:
    """종목의 최근 1년 주가를 동기화한다."""
    start = (date.today() - timedelta(days=365)).isoformat()

    try:
        if stock.market in ("NYSE", "NASDAQ"):
            df = await asyncio.to_thread(fetch_us_prices, stock.ticker, start)
        else:
            df = await asyncio.to_thread(fetch_kr_prices, stock.ticker, start)
    except Exception as e:
        return {"prices_synced": 0, "error": f"주가 조회 실패: {e}"}

    if df is None or df.empty:
        return {"prices_synced": 0, "error": "주가 데이터 없음"}

    count = 0
    for idx, row in df.iterrows():
        dt = idx.date() if hasattr(idx, "date") else idx
        stmt = insert(PriceHistory).values(
            stock_id=stock.id,
            date=dt,
            open=float(row.get("Open", 0)),
            high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)),
            close=float(row.get("Close", 0)),
            volume=int(row.get("Volume", 0)),
        ).on_conflict_do_nothing(constraint="uq_stock_date")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1

    # Stock 최신 종가 업데이트
    if not df.empty:
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else df.iloc[0]
        stock.current_price = float(latest["Close"])
        stock.change = float(latest["Close"] - prev["Close"])
        if prev["Close"] != 0:
            stock.change_percent = round(float((latest["Close"] - prev["Close"]) / prev["Close"] * 100), 2)
        db.add(stock)

    await db.commit()
    return {"prices_synced": count}
