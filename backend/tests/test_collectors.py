import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pandas as pd
from sqlalchemy import select

from app.collectors.stock_price import sync_prices
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news, strip_html
from app.collectors.disclosure import sync_disclosures
from app.collectors.exchange_rate import sync_exchange_rates
from app.config import Settings
from app.models import Stock


# ==================== Config ====================

def test_settings_defaults():
    s = Settings(database_url="postgresql+asyncpg://test:test@localhost/test")
    assert s.dart_api_key == ""
    assert s.naver_client_id == ""
    assert s.naver_client_secret == ""


# ==================== stock_price ====================

def _make_mock_df(days=3):
    today = date.today()
    dates = pd.date_range(end=today, periods=days, freq="B")
    return pd.DataFrame({
        "Open": [150.0 + i for i in range(days)],
        "High": [155.0 + i for i in range(days)],
        "Low": [149.0 + i for i in range(days)],
        "Close": [153.0 + i for i in range(days)],
        "Volume": [1000000 + i * 100000 for i in range(days)],
    }, index=dates)


@pytest.mark.asyncio
async def test_sync_prices_us_stock(db):
    """US 종목 주가 동기화"""
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalars().first()
    assert stock is not None

    with patch("app.collectors.stock_price.fetch_us_prices", return_value=_make_mock_df()):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_prices_kr_stock(db):
    """KR 종목 주가 동기화"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    mock_df = _make_mock_df()
    mock_df["Close"] = [71500, 72000, 72500]

    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=mock_df):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_prices_custom_days(db):
    """days 파라미터로 기간 지정"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=_make_mock_df(5)):
        result = await sync_prices(db, stock, days=730)

    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_prices_empty_df(db):
    """빈 DataFrame 반환 시"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=pd.DataFrame()):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_prices_none_df(db):
    """None 반환 시"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=None):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_prices_exception(db):
    """외부 API 예외 처리"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.stock_price.fetch_kr_prices", side_effect=Exception("Network error")):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_prices_single_row(db):
    """데이터 1행 — prev == latest 분기"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=_make_mock_df(1)):
        result = await sync_prices(db, stock)

    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_prices_updates_stock(db):
    """동기화 후 stock.current_price 업데이트 확인"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    mock_df = _make_mock_df(3)
    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=mock_df):
        await sync_prices(db, stock)

    assert stock.current_price == float(mock_df.iloc[-1]["Close"])


# ==================== financials ====================

@pytest.mark.asyncio
async def test_sync_financials_us_stock(db):
    """US 종목 재무지표 동기화"""
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

    assert result["financials_synced"] == 1
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_financials_empty_info(db):
    """빈 info dict 반환 시"""
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalar_one()

    with patch("app.collectors.financials.fetch_us_financials", return_value={}):
        result = await sync_financials(db, stock)

    assert result["financials_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_financials_none_info(db):
    """None 반환 시"""
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalar_one()

    with patch("app.collectors.financials.fetch_us_financials", return_value=None):
        result = await sync_financials(db, stock)

    assert result["financials_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_financials_kr_no_dart(db):
    """KR 종목 — DART 코드/키 없음"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    stock.dart_code = None

    result = await sync_financials(db, stock)
    assert result["financials_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_financials_kr_with_dart(db):
    """KR 종목 — DART 있지만 미구현"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    stock.dart_code = "00126380"

    with patch("app.collectors.financials.settings") as mock_settings:
        mock_settings.dart_api_key = "test_key"
        result = await sync_financials(db, stock)

    assert result["financials_synced"] == 0
    assert "미구현" in result.get("error", "")


@pytest.mark.asyncio
async def test_sync_financials_exception(db):
    """yfinance 예외 시"""
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalar_one()

    with patch("app.collectors.financials.fetch_us_financials", side_effect=Exception("API error")):
        result = await sync_financials(db, stock)

    assert result["financials_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_financials_partial_data(db):
    """일부 필드만 있는 경우"""
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalar_one()

    mock_info = {
        "trailingPE": 15.0,
        "marketCap": 100000000,
        # 나머지 필드 없음
    }

    with patch("app.collectors.financials.fetch_us_financials", return_value=mock_info):
        result = await sync_financials(db, stock)

    assert result["financials_synced"] == 1


# ==================== news ====================

def test_strip_html():
    assert strip_html("<b>테스트</b>") == "테스트"
    assert strip_html("plain text") == "plain text"
    assert strip_html("<a href='x'>링크</a> 텍스트") == "링크 텍스트"


@pytest.mark.asyncio
async def test_sync_news(db):
    """뉴스 동기화 — Naver API mock"""
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
         patch("app.collectors.news.fetch_naver_news", new_callable=AsyncMock, return_value=mock_response):
        mock_settings.naver_client_id = "test_id"
        mock_settings.naver_client_secret = "test_secret"
        result = await sync_news(db, stock)

    assert result["news_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_news_no_api_key(db):
    """API 키 미설정 시"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.news.settings") as mock_settings:
        mock_settings.naver_client_id = ""
        mock_settings.naver_client_secret = ""
        result = await sync_news(db, stock)

    assert result["news_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_news_exception(db):
    """API 호출 실패"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.news.settings") as mock_settings, \
         patch("app.collectors.news.fetch_naver_news", new_callable=AsyncMock, side_effect=Exception("timeout")):
        mock_settings.naver_client_id = "test_id"
        mock_settings.naver_client_secret = "test_secret"
        result = await sync_news(db, stock)

    assert result["news_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_news_bad_date(db):
    """잘못된 pubDate 형식 — fallback to datetime.now"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    mock_response = {
        "items": [
            {
                "title": "뉴스 제목",
                "link": "https://news.example.com/bad-date",
                "pubDate": "invalid-date-format",
            },
        ]
    }

    with patch("app.collectors.news.settings") as mock_settings, \
         patch("app.collectors.news.fetch_naver_news", new_callable=AsyncMock, return_value=mock_response):
        mock_settings.naver_client_id = "test_id"
        mock_settings.naver_client_secret = "test_secret"
        result = await sync_news(db, stock)

    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_news_empty_items(db):
    """items 비어있을 때"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.news.settings") as mock_settings, \
         patch("app.collectors.news.fetch_naver_news", new_callable=AsyncMock, return_value={"items": []}):
        mock_settings.naver_client_id = "test_id"
        mock_settings.naver_client_secret = "test_secret"
        result = await sync_news(db, stock)

    assert result["news_synced"] == 0
    assert "error" not in result


# ==================== disclosure ====================

@pytest.mark.asyncio
async def test_sync_disclosures_kr_stock(db):
    """KR 종목 공시 동기화"""
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
        ],
    }

    with patch("app.collectors.disclosure.fetch_dart_disclosures", new_callable=AsyncMock, return_value=mock_response), \
         patch("app.collectors.disclosure.settings", dart_api_key="test_key"):
        result = await sync_disclosures(db, stock)

    assert result["disclosures_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_disclosures_us_stock_skip(db):
    """US 종목은 공시 수집 스킵"""
    result = await db.execute(select(Stock).where(Stock.market.in_(["NYSE", "NASDAQ"])))
    stock = result.scalar_one()

    result = await sync_disclosures(db, stock)
    assert result["disclosures_synced"] == 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_disclosures_no_dart_key(db):
    """DART API 키 미설정"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    with patch("app.collectors.disclosure.settings", dart_api_key=""):
        result = await sync_disclosures(db, stock)

    assert result["disclosures_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_disclosures_no_dart_code(db):
    """DART 기업코드 미설정"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    stock.dart_code = None

    with patch("app.collectors.disclosure.settings", dart_api_key="test_key"):
        result = await sync_disclosures(db, stock)

    assert result["disclosures_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_disclosures_api_error(db):
    """DART API 오류 응답"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    stock.dart_code = "00126380"

    mock_response = {"status": "013", "message": "인증키 오류"}

    with patch("app.collectors.disclosure.fetch_dart_disclosures", new_callable=AsyncMock, return_value=mock_response), \
         patch("app.collectors.disclosure.settings", dart_api_key="test_key"):
        result = await sync_disclosures(db, stock)

    assert result["disclosures_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_disclosures_exception(db):
    """DART API 호출 예외"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    stock.dart_code = "00126380"

    with patch("app.collectors.disclosure.fetch_dart_disclosures", new_callable=AsyncMock, side_effect=Exception("timeout")), \
         patch("app.collectors.disclosure.settings", dart_api_key="test_key"):
        result = await sync_disclosures(db, stock)

    assert result["disclosures_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_disclosures_bad_date(db):
    """잘못된 날짜 형식 → fallback to datetime.now"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    stock.dart_code = "00126380"

    mock_response = {
        "status": "000",
        "list": [{"report_nm": "보고서", "rcept_dt": "bad-date", "flr_nm": "삼성전자"}],
    }

    with patch("app.collectors.disclosure.fetch_dart_disclosures", new_callable=AsyncMock, return_value=mock_response), \
         patch("app.collectors.disclosure.settings", dart_api_key="test_key"):
        result = await sync_disclosures(db, stock)

    assert "error" not in result


# ==================== exchange_rate ====================

@pytest.mark.asyncio
async def test_sync_exchange_rates(db):
    """환율 동기화"""
    mock_response = {
        "result": "success",
        "rates": {"KRW": 1350.25, "EUR": 0.92, "JPY": 154.30},
    }

    with patch("app.collectors.exchange_rate.fetch_exchange_rates", new_callable=AsyncMock, return_value=mock_response):
        result = await sync_exchange_rates(db)

    assert result["exchange_rates_synced"] == 3
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_exchange_rates_api_error(db):
    """API 응답 오류"""
    mock_response = {"result": "error"}

    with patch("app.collectors.exchange_rate.fetch_exchange_rates", new_callable=AsyncMock, return_value=mock_response):
        result = await sync_exchange_rates(db)

    assert result["exchange_rates_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_exchange_rates_exception(db):
    """API 호출 예외"""
    with patch("app.collectors.exchange_rate.fetch_exchange_rates", new_callable=AsyncMock, side_effect=Exception("timeout")):
        result = await sync_exchange_rates(db)

    assert result["exchange_rates_synced"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_sync_exchange_rates_missing_currency(db):
    """일부 통화 누락"""
    mock_response = {
        "result": "success",
        "rates": {"KRW": 1350.25},  # EUR, JPY 누락
    }

    with patch("app.collectors.exchange_rate.fetch_exchange_rates", new_callable=AsyncMock, return_value=mock_response):
        result = await sync_exchange_rates(db)

    assert result["exchange_rates_synced"] == 1


@pytest.mark.asyncio
async def test_sync_prices_zero_prev_close(db):
    """prev Close가 0인 경우 change_percent 계산 스킵"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    today = date.today()
    dates = pd.date_range(end=today, periods=2, freq="B")
    mock_df = pd.DataFrame({
        "Open": [0, 100],
        "High": [0, 105],
        "Low": [0, 95],
        "Close": [0, 100],
        "Volume": [0, 1000000],
    }, index=dates)

    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=mock_df):
        result = await sync_prices(db, stock)

    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_news_duplicate(db):
    """동일 URL 뉴스 중복 삽입 시 count 증가 안 함"""
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    mock_response = {
        "items": [
            {
                "title": "중복 뉴스",
                "link": "https://news.example.com/dup-test-unique",
                "pubDate": "Wed, 09 Apr 2026 10:00:00 +0900",
            },
        ]
    }

    with patch("app.collectors.news.settings") as mock_settings, \
         patch("app.collectors.news.fetch_naver_news", new_callable=AsyncMock, return_value=mock_response):
        mock_settings.naver_client_id = "test_id"
        mock_settings.naver_client_secret = "test_secret"
        await sync_news(db, stock)

    # 동일 뉴스 다시 삽입
    with patch("app.collectors.news.settings") as mock_settings, \
         patch("app.collectors.news.fetch_naver_news", new_callable=AsyncMock, return_value=mock_response):
        mock_settings.naver_client_id = "test_id"
        mock_settings.naver_client_secret = "test_secret"
        result2 = await sync_news(db, stock)

    # 두 번째는 0이어야 함 (중복)
    assert result2["news_synced"] == 0


# ==================== macro ====================

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest_asyncio

from app.collectors.macro import sync_macro_factors
from app.models.macro_factor import MacroFactor


@pytest_asyncio.fixture
async def db_for_macro(db, monkeypatch):
    @asynccontextmanager
    async def _session():
        yield db
    monkeypatch.setattr("app.collectors.macro.async_session", _session)
    return db


@pytest.mark.asyncio
async def test_sync_macro_factors_writes_rows(db_for_macro):
    db = db_for_macro
    # Keys are raw yfinance symbols (per YF_FACTORS), not normalized factor keys.
    # ^TNX is in tenths of a percent (Yahoo quirk) — collector divides by 10.
    fake = {
        "^VIX": [("2026-04-28", 18.7)],
        "^TNX": [("2026-04-28", 46.0)],  # → US10Y 4.6 after collector normalization
        "XLK": [("2026-04-28", 230.5)],
    }

    def fake_fetch(symbol: str, days: int):
        return fake.get(symbol, [])

    with patch("app.collectors.macro._fetch_yf", side_effect=fake_fetch):
        with patch(
            "app.collectors.macro._latest_fx", return_value={"USD/KRW": 1378.0}
        ):
            result = await sync_macro_factors()
    assert result["macro_synced"] >= 3
    rows = (await db.execute(select(MacroFactor))).scalars().all()
    factors = {r.factor for r in rows}
    assert "VIX" in factors and "US10Y" in factors and "USD/KRW" in factors
