"""Cold-call prewarm — fetch favorites at startup so first-card latency
is the warm-cache figure (sub-second), not the cold-load figure (4–21s).

Lifespan integration is wired in Phase D (`app/main.py`). This module just
provides the coroutine; tests inject a fake `favorites_loader`, production
will pass a DB-backed one. Per-ticker failures are swallowed — on-demand
fetch will retry naturally.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from app.services.external_data_adapters import get_adapter_for
from app.services.external_data_adapters.constants import PREWARM_LIMIT

logger = logging.getLogger(__name__)

# Matches SecEdgarAdapter._sem; SEC tolerates 10 req/sec, we cap at 8 in-flight.
_PREWARM_CONCURRENCY = 8


async def prewarm_favorites(
    favorites_loader: Callable[[int], Awaitable[list[str]]],
    limit: int = PREWARM_LIMIT,
) -> dict[str, int]:
    """Top-N favorites → adapter.fetch_identity + fetch_financial_series."""
    try:
        tickers = await favorites_loader(limit)
    except Exception as e:  # noqa: BLE001
        logger.warning("prewarm: favorites loader failed: %s", e)
        return {"warmed": 0, "failed": 0}

    if not tickers:
        return {"warmed": 0, "failed": 0}

    sem = asyncio.Semaphore(_PREWARM_CONCURRENCY)

    async def _warm_one(ticker: str) -> bool:
        try:
            async with sem:
                adapter = get_adapter_for(ticker)
                await adapter.fetch_identity(ticker)
                await adapter.fetch_financial_series(ticker)
            return True
        except Exception as e:  # noqa: BLE001 — degrade quietly, on-demand will retry
            logger.warning("prewarm: %s failed: %s", ticker, e)
            return False

    results = await asyncio.gather(*(_warm_one(t) for t in tickers))
    warmed = sum(1 for ok in results if ok)
    return {"warmed": warmed, "failed": len(results) - warmed}
