import asyncio
import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceHistory, Stock

logger = logging.getLogger(__name__)

# 전일 대비 이 비율 이상 변동하면 이상치로 판단
PRICE_ANOMALY_RATIO = 3.0


def fetch_us_prices(ticker: str, start: str) -> pd.DataFrame:  # pragma: no cover
    """yfinance로 US 주가 조회 (동기 함수)."""
    import yfinance as yf
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
    # yfinance returns MultiIndex columns (Price, Ticker) — flatten
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel("Ticker")
    return df


def fetch_kr_prices(ticker: str, start: str) -> pd.DataFrame:  # pragma: no cover
    """FinanceDataReader로 KR 주가 조회 (동기 함수)."""
    import FinanceDataReader as fdr
    df = fdr.DataReader(ticker, start)
    return df


async def sync_prices(db: AsyncSession, stock: Stock, days: int = 365) -> dict:
    """종목의 주가를 동기화한다. days로 기간 지정 가능."""
    start = (date.today() - timedelta(days=days)).isoformat()

    try:
        if stock.market in ("NYSE", "NASDAQ"):
            df = await asyncio.to_thread(fetch_us_prices, stock.ticker, start)
        else:
            df = await asyncio.to_thread(fetch_kr_prices, stock.ticker, start)
    except Exception as e:
        return {"prices_synced": 0, "error": f"주가 조회 실패: {e}"}

    if df is None or df.empty:
        return {"prices_synced": 0, "error": "주가 데이터 없음"}

    # 이상치 필터링: 전일 대비 300%+ 변동 시 스킵
    prev_close = None
    skipped = 0
    count = 0
    for idx, row in df.iterrows():
        dt = idx.date() if hasattr(idx, "date") else idx
        close = float(row.get("Close", 0))

        if close <= 0:
            continue

        if prev_close and prev_close > 0:
            ratio = close / prev_close
            if ratio > PRICE_ANOMALY_RATIO or ratio < (1 / PRICE_ANOMALY_RATIO):
                logger.warning(
                    "Price anomaly for %s on %s: %.2f → %.2f (%.1fx), skipping",
                    stock.ticker, dt, prev_close, close, ratio,
                )
                skipped += 1
                continue

        prev_close = close

        values = dict(
            stock_id=stock.id,
            date=dt,
            open=float(row.get("Open", 0)),
            high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)),
            close=close,
            volume=int(row.get("Volume", 0)),
        )
        stmt = insert(PriceHistory).values(**values).on_conflict_do_update(
            constraint="uq_stock_date",
            set_={k: v for k, v in values.items() if k not in ("stock_id", "date")},
        )
        await db.execute(stmt)
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
