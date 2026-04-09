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
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.disclosure import sync_disclosures
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


@pytest.mark.asyncio
async def test_sync_financials_us_stock(db):
    """US 종목 재무지표 동기화 — yfinance mock"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalar_one()

    mock_info = {
        "trailingPE": 28.5,
        "priceToBook": 45.2,
        "returnOnEquity": 0.152,
        "dividendYield": 0.006,
        "marketCap": 3000000000000,
        "totalRevenue": 390000000000,
        "operatingIncome": 120000000000,
        "netIncome": 95000000000,
    }

    with patch("app.collectors.financials.fetch_us_financials", return_value=mock_info):
        result = await sync_financials(db, stock)

    assert result["financials_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_news(db):
    """뉴스 동기화 — Naver API mock"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    mock_response = {
        "items": [
            {
                "title": "<b>삼성전자</b> HBM 수주 확대",
                "link": "https://news.example.com/1",
                "pubDate": "Wed, 09 Apr 2026 10:00:00 +0900",
            },
            {
                "title": "<b>삼성전자</b> 실적 전망",
                "link": "https://news.example.com/2",
                "pubDate": "Tue, 08 Apr 2026 09:00:00 +0900",
            },
        ]
    }

    with patch("app.collectors.news.settings") as mock_settings, \
         patch("app.collectors.news.fetch_naver_news", return_value=mock_response):
        mock_settings.naver_client_id = "test_id"
        mock_settings.naver_client_secret = "test_secret"
        result = await sync_news(db, stock)

    assert result["news_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_disclosures_kr_stock(db):
    """KR 종목 공시 동기화 — DART API mock"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    stock.dart_code = "00126380"

    mock_response = {
        "status": "000",
        "list": [
            {
                "report_nm": "분기보고서 (2026.03)",
                "rcept_dt": "20260401",
                "flr_nm": "삼성전자",
            },
            {
                "report_nm": "주요사항보고서(자기주식취득결정)",
                "rcept_dt": "20260325",
                "flr_nm": "삼성전자",
            },
        ],
    }

    with patch("app.collectors.disclosure.fetch_dart_disclosures", return_value=mock_response), \
         patch("app.collectors.disclosure.settings", dart_api_key="test_key"):
        result = await sync_disclosures(db, stock)

    assert result["disclosures_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_disclosures_us_stock_skip(db):
    """US 종목은 공시 수집 스킵"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalar_one()

    result = await sync_disclosures(db, stock)
    assert result["disclosures_synced"] == 0
    assert "error" not in result
