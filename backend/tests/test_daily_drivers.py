from datetime import date

import pytest

from app.models import DailyPriceDriver, PriceHistory, Stock
from app.services.analyst.daily_drivers import ensure_daily_driver, latest_completed_trade_date


@pytest.mark.asyncio
async def test_latest_completed_trade_date_ignores_today(db):
    stock = Stock(ticker="DRV1", name="Driver Test", market="US", sector="Tech", current_price=10)
    db.add(stock)
    await db.flush()
    db.add_all(
        [
            PriceHistory(
                stock_id=stock.id,
                date=date(2026, 5, 21),
                open=10,
                high=11,
                low=9,
                close=10,
                volume=100,
            ),
            PriceHistory(
                stock_id=stock.id,
                date=date.today(),
                open=10,
                high=11,
                low=9,
                close=11,
                volume=100,
            ),
        ]
    )
    await db.commit()

    assert await latest_completed_trade_date(db, stock.id) == date(2026, 5, 21)


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
