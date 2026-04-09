from app.config import Settings


def test_settings_defaults():
    s = Settings(database_url="postgresql+asyncpg://test:test@localhost/test")
    assert s.dart_api_key == ""
    assert s.naver_client_id == ""
    assert s.naver_client_secret == ""


import pytest
import pytest_asyncio
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import pandas as pd

from app.collectors.stock_price import sync_prices
from app.models import Stock


@pytest.mark.asyncio
async def test_sync_prices_us_stock(db):
    """US 종목 주가 동기화 — yfinance mock 사용"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalars().first()
    assert stock is not None, "No US stock found in DB"

    today = date.today()
    dates = pd.date_range(end=today, periods=3, freq="B")
    mock_df = pd.DataFrame({
        "Open": [150.0, 151.0, 152.0],
        "High": [155.0, 156.0, 157.0],
        "Low": [149.0, 150.0, 151.0],
        "Close": [153.0, 154.0, 155.0],
        "Volume": [1000000, 1100000, 1200000],
    }, index=dates)

    with patch("app.collectors.stock_price.fetch_us_prices", return_value=mock_df):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_prices_kr_stock(db):
    """KR 종목 주가 동기화 — FDR mock 사용"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    today = date.today()
    dates = pd.date_range(end=today, periods=3, freq="B")
    mock_df = pd.DataFrame({
        "Open": [71000, 71500, 72000],
        "High": [72000, 72500, 73000],
        "Low": [70500, 71000, 71500],
        "Close": [71500, 72000, 72500],
        "Volume": [5000000, 5500000, 6000000],
    }, index=dates)

    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=mock_df):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] >= 0
    assert "error" not in result
