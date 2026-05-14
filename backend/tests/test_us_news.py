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


# Fixture URLs는 publisher_whitelist (2026-05-14 Codex 권고) 통과해야 insert
# 된다. example.com 처럼 untrusted host 는 자동 drop. 트레이더 카드에 신뢰
# 매체만 노출하는 정책이라 test도 같은 약속을 따른다.
SAMPLE_YFINANCE_NEWS = [
    {
        "title": "Tesla Q1 earnings beat expectations",
        "link": "https://www.reuters.com/business/tesla-q1",
        "publisher": "Reuters",
        "providerPublishTime": int(time.time()) - 3600,
    },
    {
        "title": "Tesla launches new Model Y",
        "url": "https://www.bloomberg.com/news/articles/tesla-model-y",
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
        {"title": "No timestamp", "link": "https://www.reuters.com/no-ts", "publisher": "Test"},
    ])
    async def test_missing_timestamp(self, mock_fetch):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute = AsyncMock(return_value=result_mock)

        result = await _sync_yfinance_news(db, _make_stock())
        assert result["news_synced"] == 1

    @pytest.mark.asyncio
    @patch("app.collectors.news._fetch_yfinance_news", return_value=[
        {"title": "Spam aggregator article", "link": "https://example.com/spam", "publisher": "Spam"},
        {"title": "Untrusted blog post", "link": "https://random-blog.tistory.com/abc", "publisher": "blog"},
    ])
    async def test_untrusted_publishers_dropped(self, mock_fetch):
        """publisher_whitelist 통과 못한 host는 DB insert 전 drop."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1  # if insert happened, this would yield 2
        db.execute = AsyncMock(return_value=result_mock)

        result = await _sync_yfinance_news(db, _make_stock())
        assert result["news_synced"] == 0
        # insert 자체가 호출되지 않아야 함 — filter 가 먼저 차단
        assert db.execute.await_count == 0


class TestSyncNewsRouting:
    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, return_value={"scraped": 0})
    @patch("app.collectors.news._sync_newsapi", new_callable=AsyncMock, return_value={"news_synced": 0})
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock, return_value={"news_synced": 5})
    @patch("app.collectors.news._sync_naver_news", new_callable=AsyncMock)
    async def test_us_stock_uses_yfinance(self, mock_naver, mock_yf, mock_newsapi, mock_scrape):
        db = AsyncMock()
        result = await sync_news(db, _make_stock("TSLA", "NASDAQ"))
        mock_yf.assert_called_once()
        mock_naver.assert_not_called()
        assert result["news_synced"] == 5

    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, return_value={"scraped": 0})
    @patch("app.collectors.news._sync_naver_finance_news", new_callable=AsyncMock, return_value={"news_synced": 5})
    @patch("app.collectors.news._sync_google_news_kr", new_callable=AsyncMock, return_value={"news_synced": 0})
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock)
    @patch("app.collectors.news._sync_naver_news", new_callable=AsyncMock, return_value={"news_synced": 10})
    async def test_kr_stock_uses_naver(self, mock_naver, mock_yf, mock_gnews, mock_naver_finance, mock_scrape):
        db = AsyncMock()
        result = await sync_news(db, _make_stock("005930", "KRX"))
        mock_naver.assert_called_once()
        mock_gnews.assert_called_once()
        mock_naver_finance.assert_called_once()
        mock_yf.assert_not_called()
        assert result["news_synced"] == 15  # 10 naver_open + 5 naver_finance + 0 gnews


class TestSyncNewsWithScraping:
    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, return_value={"scraped": 3})
    @patch("app.collectors.news._sync_newsapi", new_callable=AsyncMock, return_value={"news_synced": 10})
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock, return_value={"news_synced": 5})
    async def test_us_sync_calls_scraper(self, mock_yf, mock_newsapi, mock_scrape):
        db = AsyncMock()
        stock = _make_stock("TSLA", "NASDAQ")
        result = await sync_news(db, stock)

        mock_scrape.assert_called_once_with(db, stock.id)
        assert result["news_synced"] == 15
        assert result["scraped"] == 3

    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, return_value={"scraped": 5})
    @patch("app.collectors.news._sync_naver_finance_news", new_callable=AsyncMock, return_value={"news_synced": 3})
    @patch("app.collectors.news._sync_google_news_kr", new_callable=AsyncMock, return_value={"news_synced": 0})
    @patch("app.collectors.news._sync_naver_news", new_callable=AsyncMock, return_value={"news_synced": 20})
    async def test_kr_sync_calls_scraper(self, mock_naver, mock_gnews, mock_naver_finance, mock_scrape):
        db = AsyncMock()
        stock = _make_stock("005930", "KRX")
        result = await sync_news(db, stock)

        mock_scrape.assert_called_once_with(db, stock.id)
        assert result["news_synced"] == 23  # 20 naver_open + 0 gnews + 3 naver_finance
        assert result["scraped"] == 5

    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, side_effect=Exception("scrape error"))
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock, return_value={"news_synced": 5})
    @patch("app.collectors.news._sync_newsapi", new_callable=AsyncMock, return_value={"news_synced": 0})
    async def test_scraper_failure_does_not_break_sync(self, mock_newsapi, mock_yf, mock_scrape):
        db = AsyncMock()
        stock = _make_stock("TSLA", "NASDAQ")
        result = await sync_news(db, stock)

        assert result["news_synced"] == 5
        assert result["scraped"] == 0
