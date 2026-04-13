"""Scheduler 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scheduler import _sync_single_stock, scheduled_sync_job, init_scheduler


def _make_stock(ticker="005930", name="삼성전자"):
    s = MagicMock()
    s.id = 1
    s.ticker = ticker
    s.name = name
    s.market = "KRX"
    s.current_price = 71500
    s.change_percent = -1.65
    return s


class TestSyncSingleStock:
    @pytest.mark.asyncio
    @patch("app.scheduler.async_session")
    @patch("app.scheduler.sync_prices", new_callable=AsyncMock)
    @patch("app.scheduler.sync_financials", new_callable=AsyncMock)
    @patch("app.scheduler.sync_news", new_callable=AsyncMock)
    @patch("app.scheduler.sync_disclosures", new_callable=AsyncMock)
    @patch("app.scheduler.settings")
    async def test_success_no_llm(self, mock_settings, mock_disc, mock_news, mock_fin, mock_prices, mock_session):
        mock_settings.llm_api_key = ""
        mock_prices.return_value = {"prices_synced": 10}
        mock_fin.return_value = {"financials_synced": 1}
        mock_news.return_value = {"news_synced": 5}
        mock_disc.return_value = {"disclosures_synced": 0, "error": "DART 키 미설정"}

        db_mock = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_mock)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _sync_single_stock(_make_stock())

        assert result["ticker"] == "005930"
        assert result["prices"] == 10
        assert result["analysis"] is False
        assert "DART 키 미설정" in result["errors"]

    @pytest.mark.asyncio
    @patch("app.scheduler.async_session")
    @patch("app.scheduler.sync_prices", new_callable=AsyncMock)
    @patch("app.scheduler.sync_financials", new_callable=AsyncMock)
    @patch("app.scheduler.sync_news", new_callable=AsyncMock)
    @patch("app.scheduler.sync_disclosures", new_callable=AsyncMock)
    @patch("app.scheduler.analyze_stock", new_callable=AsyncMock)
    @patch("app.scheduler.get_adapter")
    @patch("app.scheduler.settings")
    async def test_success_with_llm(self, mock_settings, mock_get_adapter, mock_analyze, mock_disc, mock_news, mock_fin, mock_prices, mock_session):
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_provider = "azure_openai"
        mock_prices.return_value = {"prices_synced": 10}
        mock_fin.return_value = {"financials_synced": 1}
        mock_news.return_value = {"news_synced": 5}
        mock_disc.return_value = {"disclosures_synced": 3}
        mock_analyze.return_value = {"analysis_created": True}

        db_mock = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_mock)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _sync_single_stock(_make_stock())

        assert result["analysis"] is True
        mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.scheduler.async_session")
    @patch("app.scheduler.sync_prices", new_callable=AsyncMock, side_effect=Exception("boom"))
    @patch("app.scheduler.settings")
    async def test_exception_handled(self, mock_settings, mock_prices, mock_session):
        mock_settings.llm_api_key = ""
        db_mock = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_mock)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _sync_single_stock(_make_stock())

        assert "boom" in result["errors"][0]


class TestScheduledSyncJob:
    @pytest.mark.asyncio
    @patch("app.scheduler._sync_single_stock", new_callable=AsyncMock)
    @patch("app.scheduler.sync_exchange_rates", new_callable=AsyncMock)
    @patch("app.scheduler.async_session")
    async def test_syncs_favorited_stocks(self, mock_session, mock_rates, mock_single):
        stock1 = _make_stock("005930")
        stock2 = _make_stock("TSLA", "Tesla")

        # First call: query favorites
        db_fav = AsyncMock()
        fav_result = MagicMock()
        fav_result.scalars.return_value.all.return_value = [stock1, stock2]
        db_fav.execute = AsyncMock(return_value=fav_result)

        # Second call: exchange rates
        db_rates = AsyncMock()

        call_count = 0
        async def session_context():
            nonlocal call_count
            call_count += 1
            return db_fav if call_count == 1 else db_rates

        mock_session.return_value.__aenter__ = AsyncMock(side_effect=[db_fav, db_rates])
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_single.return_value = {"ticker": "005930", "errors": []}
        mock_rates.return_value = {"exchange_rates_synced": 3}

        await scheduled_sync_job()

        assert mock_single.call_count == 2
        mock_rates.assert_called_once()


class TestInitScheduler:
    @patch("app.scheduler.scheduler")
    @patch("app.scheduler.settings")
    def test_disabled(self, mock_settings, mock_sched):
        mock_settings.scheduler_enabled = False
        init_scheduler()
        mock_sched.start.assert_not_called()

    @patch("app.scheduler.scheduler")
    @patch("app.scheduler.settings")
    def test_enabled(self, mock_settings, mock_sched):
        mock_settings.scheduler_enabled = True
        mock_settings.scheduler_morning = "08:00"
        mock_settings.scheduler_evening = "18:00"
        mock_settings.scheduler_timezone = "Asia/Seoul"
        init_scheduler()
        assert mock_sched.add_job.call_count == 2
        mock_sched.start.assert_called_once()
