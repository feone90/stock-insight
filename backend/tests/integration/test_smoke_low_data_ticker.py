"""Low-data ticker smoke — graceful degrade without raising.

Spec §7: pick a recent IPO or thinly-covered ticker → assert technical=None
etc. without raising. The seed set is small (KR 005930 + US TSLA), so this
test is **opt-in via `LOW_DATA_TICKER` env var** — set it to a ticker that
exists in your DB with sparse fundamentals/history, and the test will
verify analyze() degrades cleanly instead of bombing.

Run with:
    LOW_DATA_TICKER=XXXX uv run python -m pytest -m smoke -v
"""
import os

import pytest

from app.config import settings
from app.schemas.card import StockCard
from app.services.analyst.engine import analyze, is_analyzable


@pytest.mark.smoke
@pytest.mark.skipif(
    not settings.tavily_api_key,
    reason="TAVILY_API_KEY not configured; smoke needs real keys",
)
@pytest.mark.asyncio
async def test_smoke_low_data_ticker_degrades_gracefully():
    ticker = os.getenv("LOW_DATA_TICKER")
    if not ticker:
        pytest.skip("LOW_DATA_TICKER env var not set — opt-in only")

    ok, _reason = await is_analyzable(ticker)
    if not ok:
        pytest.skip(f"{ticker} not analyzable (no price/history) — pick another")

    card = await analyze(ticker)
    assert isinstance(card, StockCard)
    assert card.ticker == ticker.upper()

    # Card structure must still validate even if data sections are stubs.
    # Either the data was sufficient (real values) or it was sparse
    # (None values + stub summary line) — both are valid post-refactor.
    if card.technical.rsi_14 is None:
        assert card.technical.summary_line  # always non-empty
    if card.macro.vix is None:
        assert card.macro.one_line  # always non-empty

    # Persona contract still enforced even with sparse data.
    assert len(card.thesis.supports) >= 3
    assert len(card.thesis.opposes) >= 2
    assert len(card.thesis.scenarios) == 3
