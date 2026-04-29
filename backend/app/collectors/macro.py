"""Macro factor daily collector. Fetches VIX, US10Y, sector ETFs, USD/KRW."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import async_session
from app.models.exchange_rate import ExchangeRate
from app.models.macro_factor import MacroFactor

logger = logging.getLogger(__name__)

# yfinance ticker → factor key
YF_FACTORS = {
    "^VIX": "VIX",
    "^TNX": "US10Y",  # CBOE 10-Year Treasury Note Yield (in tenths of a percent)
    "XLK": "XLK",  # Tech sector ETF
    "XLF": "XLF",  # Financials
    "XLE": "XLE",  # Energy
    "DX-Y.NYB": "DXY",  # Dollar index
}


def _fetch_yf(symbol: str, days: int = 7) -> list[tuple[str, float]]:
    """Returns list of (YYYY-MM-DD, close) for the past `days`."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{days}d")
        if hist.empty:
            return []
        out = []
        for ts, row in hist.iterrows():
            out.append((ts.date().isoformat(), float(row["Close"])))
        return out
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", symbol, e)
        return []


async def _latest_fx() -> dict[str, float]:
    """Pull latest USD/KRW (and others) from exchange_rates table."""
    async with async_session() as db:
        rows = (
            await db.execute(
                select(ExchangeRate).order_by(ExchangeRate.date.desc()).limit(10)
            )
        ).scalars().all()
        out: dict[str, float] = {}
        for r in rows:
            if r.currency_pair not in out:
                out[r.currency_pair] = r.rate
        return out


async def sync_macro_factors() -> dict:
    """Idempotent upsert of all configured macro factors."""
    synced = 0
    today = date.today()
    async with async_session() as db:
        # yfinance-sourced factors
        for symbol, key in YF_FACTORS.items():
            history = _fetch_yf(symbol, days=7)
            for d_str, value in history:
                d = date.fromisoformat(d_str)
                # Yahoo TNX is *10 actual yield. Normalize.
                if key == "US10Y":
                    value = value / 10.0
                stmt = (
                    insert(MacroFactor)
                    .values(factor=key, date=d, value=value, source="market_data")
                    .on_conflict_do_update(
                        index_elements=["factor", "date"],
                        set_={"value": value, "fetched_at": datetime.utcnow()},
                    )
                )
                await db.execute(stmt)
                synced += 1

        # FX from existing collector cache
        fx = await _latest_fx()
        for pair, rate in fx.items():
            stmt = (
                insert(MacroFactor)
                .values(factor=pair, date=today, value=rate, source="market_data")
                .on_conflict_do_update(
                    index_elements=["factor", "date"],
                    set_={"value": rate, "fetched_at": datetime.utcnow()},
                )
            )
            await db.execute(stmt)
            synced += 1

        await db.commit()
    logger.info("macro factors synced: %d", synced)
    return {"macro_synced": synced}
