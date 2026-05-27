import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models import DailyPriceDriver, Favorite, PriceHistory, Stock
from app.services.analyst.daily_drivers import (
    completed_trade_dates,
    ensure_daily_driver,
    latest_completed_trade_date,
    local_today,
    run_daily_driver_batch,
)


def test_local_today_uses_scheduler_timezone():
    utc_late_night = datetime(2026, 5, 26, 23, 10, tzinfo=timezone.utc)

    assert local_today(utc_late_night) == date(2026, 5, 27)


@pytest.mark.asyncio
async def test_latest_completed_trade_date_ignores_today(db):
    today = local_today()
    previous = today - timedelta(days=6)
    stock = Stock(ticker="DRV1", name="Driver Test", market="US", sector="Tech", current_price=10)
    db.add(stock)
    await db.flush()
    db.add_all(
        [
            PriceHistory(
                stock_id=stock.id,
                date=previous,
                open=10,
                high=11,
                low=9,
                close=10,
                volume=100,
            ),
            PriceHistory(
                stock_id=stock.id,
                date=today,
                open=10,
                high=11,
                low=9,
                close=11,
                volume=100,
            ),
        ]
    )
    await db.commit()

    assert await latest_completed_trade_date(db, stock.id) == previous


@pytest.mark.asyncio
async def test_completed_trade_dates_returns_recent_missing_window(db):
    today = local_today()
    stock = Stock(ticker="DRVWIN", name="Driver Window", market="US", sector="Tech", current_price=10)
    db.add(stock)
    await db.flush()
    db.add_all(
        [
            PriceHistory(
                stock_id=stock.id,
                date=today - timedelta(days=8),
                open=10,
                high=11,
                low=9,
                close=10,
                volume=100,
            ),
            PriceHistory(
                stock_id=stock.id,
                date=today - timedelta(days=2),
                open=10,
                high=11,
                low=9,
                close=10,
                volume=100,
            ),
            PriceHistory(
                stock_id=stock.id,
                date=today - timedelta(days=1),
                open=10,
                high=11,
                low=9,
                close=11,
                volume=100,
            ),
            PriceHistory(
                stock_id=stock.id,
                date=today,
                open=11,
                high=12,
                low=10,
                close=12,
                volume=100,
            ),
        ]
    )
    await db.commit()

    assert await completed_trade_dates(db, stock.id, days=7) == [
        today - timedelta(days=2),
        today - timedelta(days=1),
    ]


@pytest.mark.asyncio
async def test_ensure_daily_driver_skips_existing_without_llm(db):
    stock = Stock(ticker="DRV2", name="Driver Test", market="US", sector="Tech", current_price=10)
    db.add(stock)
    await db.flush()
    existing = DailyPriceDriver(
        stock_id=stock.id,
        trade_date=date(2026, 5, 21),
        direction="positive",
        keywords=["OpenAI 계약 기대"],
        summary="AI 계약 기대가 주가를 밀어 올림",
        evidence={"news": []},
        confidence="medium",
        source_hash="abc",
        model_version="daily_driver_v1",
    )
    db.add(existing)
    await db.commit()

    assert await ensure_daily_driver(db, stock, date(2026, 5, 21)) is None


@pytest.mark.asyncio
async def test_run_daily_driver_batch_backfills_late_price_rows(db, monkeypatch):
    today = local_today()
    stock = Stock(ticker="DRVBACK", name="Driver Backfill", market="US", sector="Tech", current_price=10)
    db.add(stock)
    await db.flush()
    db.add(Favorite(user_id="tester", stock_id=stock.id))
    db.add_all(
        [
            PriceHistory(
                stock_id=stock.id,
                date=today - timedelta(days=3),
                open=10,
                high=11,
                low=9,
                close=10,
                volume=100,
            ),
            PriceHistory(
                stock_id=stock.id,
                date=today - timedelta(days=1),
                open=10,
                high=12,
                low=9,
                close=12,
                volume=100,
            ),
        ]
    )
    db.add(
        DailyPriceDriver(
            stock_id=stock.id,
            trade_date=today - timedelta(days=3),
            direction="neutral",
            keywords=["기존 원인"],
            summary="이미 만들어진 원인",
            evidence={"news": []},
            confidence="medium",
            source_hash="existing",
            model_version="daily_driver_v1",
        )
    )
    await db.commit()

    @asynccontextmanager
    async def _session():
        yield db

    adapter = type("Adapter", (), {})()
    adapter.generate_json = AsyncMock(
        return_value=json.dumps(
            {
                "direction": "positive",
                "keywords": ["늦은 가격 반영"],
                "summary": "뒤늦게 들어온 가격 row도 다음 배치에서 회수한다.",
                "confidence": "high",
            },
            ensure_ascii=False,
        )
    )
    monkeypatch.setattr("app.services.analyst.daily_drivers.async_session", _session)
    monkeypatch.setattr("app.services.analyst.daily_drivers.can_proceed", lambda: True)
    monkeypatch.setattr("app.services.analyst.daily_drivers.get_analyst_adapter", lambda: adapter)

    result = await run_daily_driver_batch(limit=10, days=7)

    assert result.status == "ok"
    assert result.created == 1
    assert result.skipped >= 1
    rows = (
        await db.execute(
            select(DailyPriceDriver).where(
                DailyPriceDriver.stock_id == stock.id,
                DailyPriceDriver.trade_date == today - timedelta(days=1),
            )
        )
    ).scalars().all()
    assert rows[0].keywords == ["늦은 가격 반영"]
    adapter.generate_json.assert_awaited_once()
