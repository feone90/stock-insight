"""US 뉴스 수집 테스트 (yfinance 기반)."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.collectors.news import _sync_yfinance_news, sync_news


def _make_stock(ticker="TSLA", market="NASDAQ"):
    s = MagicMock()
    s.id = 1
    s.ticker = ticker
    s.name = "Tesla"
    s.market = market
    return s


SAMPLE_YFINANCE_NEWS = [
    {
        "title": "Tesla Q1 earnings beat expectations",
        "link": "https://example.com/tesla-q1",
        "publisher": "Reuters",
        "providerPublishTime": int(time.time()) - 3600,
    },
    {
        "title": "Tesla launches new Model Y",
        "url": "https://example.com/tesla-model-y",
        "publisher": "Bloomberg",
        "providerPublishTime": int(time.time()) - 7200,
    },
]


class TestSyncYfinanceNews:
    @pytest.mark.asyncio
    @patch("app.collectors.news._fetch_yfinance_news", return_value=SAMPLE_YFINANCE_NEWS)
    async def test_success(self, mock_fetch):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute = AsyncMock(return_value=result_mock)

        result = await _sync_yfinance_news(db, _make_stock())

        assert result["news_synced"] == 2
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.collectors.news._fetch_yfinance_news", return_value=[])
    async def test_empty_news(self, mock_fetch):
        db = AsyncMock()
        result = await _sync_yfinance_news(db, _make_stock())
        assert result["news_synced"] == 0

    @pytest.mark.asyncio
    @patch("app.collectors.news._fetch_yfinance_news", side_effect=Exception("network error"))
    async def test_exception(self, mock_fetch):
        db = AsyncMock()
        result = await _sync_yfinance_news(db, _make_stock())
        assert result["news_synced"] == 0
        assert "US 뉴스 조회 실패" in result["error"]

    @pytest.mark.asyncio
    @patch("app.collectors.news._fetch_yfinance_news", return_value=[{"title": "", "link": ""}])
    async def test_skips_empty_title_url(self, mock_fetch):
        db = AsyncMock()
        result = await _sync_yfinance_news(db, _make_stock())
        assert result["news_synced"] == 0

    @pytest.mark.asyncio
    @patch("app.collectors.news._fetch_yfinance_news", return_value=[
        {"title": "No timestamp", "link": "https://example.com/no-ts", "publisher": "Test"},
    ])
    async def test_missing_timestamp(self, mock_fetch):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute = AsyncMock(return_value=result_mock)

        result = await _sync_yfinance_news(db, _make_stock())
        assert result["news_synced"] == 1


class TestSyncNewsRouting:
    @pytest.mark.asyncio
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock, return_value={"news_synced": 5})
    @patch("app.collectors.news._sync_naver_news", new_callable=AsyncMock)
    async def test_us_stock_uses_yfinance(self, mock_naver, mock_yf):
        db = AsyncMock()
        result = await sync_news(db, _make_stock("TSLA", "NASDAQ"))
        mock_yf.assert_called_once()
        mock_naver.assert_not_called()
        assert result["news_synced"] == 5

    @pytest.mark.asyncio
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock)
    @patch("app.collectors.news._sync_naver_news", new_callable=AsyncMock, return_value={"news_synced": 10})
    async def test_kr_stock_uses_naver(self, mock_naver, mock_yf):
        db = AsyncMock()
        result = await sync_news(db, _make_stock("005930", "KRX"))
        mock_naver.assert_called_once()
        mock_yf.assert_not_called()
        assert result["news_synced"] == 10
