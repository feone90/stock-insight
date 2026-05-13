import asyncio
import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.markets import is_kr
from app.models import PriceHistory, Stock

logger = logging.getLogger(__name__)

# 전일 대비 이 비율 이상 변동하면 이상치로 판단 (1.5 = 50% 이상 변동)
PRICE_ANOMALY_RATIO = 1.5


def _flatten_multiindex_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """yfinance가 single ticker도 MultiIndex 컬럼으로 반환. level 이름이
    'Ticker'/'Tickers'/None 사이로 버전마다 흔들려서 level 이름으로 drop하면
    silently 실패하고 row[col]이 Series로 잡힘 (NVDA/AMD sync에서 본 버그).

    안전한 평탄화: 단일 ticker fetch → ticker level은 unique value 1개. 그
    level을 찾아 drop. 못 찾으면 첫 level fallback.
    """
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    ticker_level = next(
        (
            lvl for lvl in range(df.columns.nlevels)
            if df.columns.get_level_values(lvl).nunique() == 1
        ),
        None,
    )
    df.columns = df.columns.droplevel(ticker_level if ticker_level is not None else 0)
    return df


def fetch_us_prices(ticker: str, start: str) -> pd.DataFrame:
    """yfinance로 US 주가 조회 (동기 함수)."""
    import yfinance as yf
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
    if df is None or df.empty:
        return df
    return _flatten_multiindex_columns(df, ticker)


def fetch_kr_prices(ticker: str, start: str) -> pd.DataFrame:  # pragma: no cover
    """FinanceDataReader로 KR 주가 조회 (동기 함수)."""
    import FinanceDataReader as fdr
    df = fdr.DataReader(ticker, start)
    return df


async def sync_prices(db: AsyncSession, stock: Stock, days: int = 365) -> dict:
    """종목의 주가를 동기화한다. days로 기간 지정 가능."""
    start = (date.today() - timedelta(days=days)).isoformat()

    try:
        if is_kr(stock.market):
            df = await asyncio.to_thread(fetch_kr_prices, stock.ticker, start)
        else:
            df = await asyncio.to_thread(fetch_us_prices, stock.ticker, start)
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
