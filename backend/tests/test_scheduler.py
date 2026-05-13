"""Scheduler 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.scheduler import _sync_single_stock, scheduled_sync_job, init_scheduler, cleanup_old_news_content


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
    @patch("app.scheduler.cleanup_old_news_content", new_callable=AsyncMock, return_value={"cleaned": 0})
    @patch("app.scheduler._sync_single_stock", new_callable=AsyncMock)
    @patch("app.scheduler.sync_exchange_rates", new_callable=AsyncMock)
    @patch("app.scheduler.async_session")
    async def test_syncs_favorited_stocks(self, mock_session, mock_rates, mock_single, mock_cleanup):
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
        # v2 split cron strings
        mock_settings.schedule_kr_morning = "30 8 * * 1-5"
        mock_settings.schedule_kr_afternoon = "0 16 * * 1-5"
        mock_settings.schedule_us_evening = "0 7 * * 1-5"
        mock_settings.schedule_us_night = "30 22 * * 1-5"
        init_scheduler()
        # 2 phase A + 4 v2 + 1 universe refresh + 1 sector match + 1 sec 8-K
        # + 1 news + 1 inverse-verify + 1 fred + 1 truth_social pipeline
        # (added with political signals) = 13 jobs
        assert mock_sched.add_job.call_count == 13
        mock_sched.start.assert_called_once()


class TestCleanupOldNewsContent:
    @pytest.mark.asyncio
    @patch("app.scheduler.settings")
    @patch("app.scheduler.async_session")
    async def test_cleans_old_content(self, mock_session, mock_settings):
        mock_settings.news_content_retention_days = 30

        db_mock = AsyncMock()
        exec_result = MagicMock()
        exec_result.rowcount = 15
        db_mock.execute = AsyncMock(return_value=exec_result)

        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_mock)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await cleanup_old_news_content()

        assert result["cleaned"] == 15
        db_mock.execute.assert_called_once()
        db_mock.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.scheduler.settings")
    @patch("app.scheduler.async_session")
    async def test_nothing_to_clean(self, mock_session, mock_settings):
        mock_settings.news_content_retention_days = 30

        db_mock = AsyncMock()
        exec_result = MagicMock()
        exec_result.rowcount = 0
        db_mock.execute = AsyncMock(return_value=exec_result)

        mock_session.return_value.__aenter__ = AsyncMock(return_value=db_mock)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await cleanup_old_news_content()

        assert result["cleaned"] == 0


# ============================================================================
# v2 KR/US analysis batch (split scheduler)
# ============================================================================

import pytest_asyncio  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from app.models import Favorite, Stock as _Stock  # noqa: E402
from app.scheduler import run_kr_analysis_batch, run_us_analysis_batch  # noqa: E402


@pytest_asyncio.fixture
async def db_for_v2_batch(db, monkeypatch):
    """Patch async_session for both dedup helper and engine entry point."""

    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("app.services.analyst.dedup.async_session", _session)
    monkeypatch.setattr("app.services.analyst.engine.async_session", _session)
    return db


@pytest.mark.asyncio
async def test_run_kr_batch_analyzes_only_kr_unique(db_for_v2_batch, monkeypatch):
    db = db_for_v2_batch
    s1 = _Stock(ticker="KR1", name="x", market="KRX", sector="x")
    s2 = _Stock(ticker="KR2", name="x", market="KOSPI", sector="x")
    s3 = _Stock(ticker="US1", name="x", market="NASDAQ", sector="x")
    db.add_all([s1, s2, s3])
    await db.flush()
    db.add_all([
        Favorite(user_id="u1", stock_id=s1.id),
        Favorite(user_id="u2", stock_id=s1.id),  # dup
        Favorite(user_id="u1", stock_id=s2.id),
        Favorite(user_id="u1", stock_id=s3.id),
    ])
    await db.commit()

    called: list[str] = []

    async def fake_analyze(ticker: str):
        called.append(ticker)

    monkeypatch.setattr("app.scheduler.analyze", fake_analyze)
    monkeypatch.setattr("app.scheduler.can_proceed", lambda: True)

    await run_kr_analysis_batch()
    # Seed data may include other KR favorites — assert ours are present, US is absent.
    assert "KR1" in called
    assert "KR2" in called
    assert "US1" not in called


@pytest.mark.asyncio
async def test_run_us_batch_analyzes_only_us_unique(db_for_v2_batch, monkeypatch):
    db = db_for_v2_batch
    db.add_all([
        _Stock(ticker="US10", name="x", market="NASDAQ", sector="x"),
        _Stock(ticker="US20", name="x", market="NYSE", sector="x"),
        _Stock(ticker="KR_X", name="x", market="KOSPI", sector="x"),
    ])
    await db.flush()
    rows = (await db.execute(select(_Stock))).scalars().all()
    for r in rows:
        if r.ticker in {"US10", "US20", "KR_X"}:
            db.add(Favorite(user_id="u", stock_id=r.id))
    await db.commit()

    called: list[str] = []
    monkeypatch.setattr("app.scheduler.analyze", lambda t: _push(called, t))
    monkeypatch.setattr("app.scheduler.can_proceed", lambda: True)

    await run_us_analysis_batch()
    assert "US10" in called
    assert "US20" in called
    assert "KR_X" not in called


@pytest.mark.asyncio
async def test_kr_batch_skips_when_budget_exhausted(db_for_v2_batch, monkeypatch):
    """can_proceed=False short-circuits the batch — no analyze calls."""
    called: list[str] = []
    monkeypatch.setattr("app.scheduler.analyze", lambda t: _push(called, t))
    monkeypatch.setattr("app.scheduler.can_proceed", lambda: False)

    await run_kr_analysis_batch()
    assert called == []


async def _push(target: list, ticker: str):
    target.append(ticker)
