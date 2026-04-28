"""Cross-ticker (US market) smoke for the v2 analyst engine.

Spec §7 calls for `test_smoke_aapl.py`, but only TSLA is in the seed dataset
right now. Same intent: verify the refactored compose flow holds up on a
non-KR ticker.

Run only with:
    cd backend && uv run python -m pytest -m smoke -v
"""
import pytest

from app.config import settings
from app.schemas.card import StockCard
from app.services.analyst.engine import analyze


_VALID_SOURCE_TYPES = {
    "db", "market_data", "news", "disclosure", "web", "curated_relation",
}


@pytest.mark.smoke
@pytest.mark.skipif(
    not settings.tavily_api_key,
    reason="TAVILY_API_KEY not configured; smoke needs real keys",
)
@pytest.mark.asyncio
async def test_smoke_analyze_tsla_produces_valid_card():
    """End-to-end research → data + analyst → compose for TSLA."""
    card = await analyze("TSLA")
    assert isinstance(card, StockCard)
    assert card.ticker == "TSLA"
    assert card.persona_version == "analyst_v1"
    assert card.schema_version == "v2"

    # Persona contract still holds across markets
    assert len(card.thesis.supports) >= 3
    assert len(card.thesis.opposes) >= 2
    assert len(card.thesis.scenarios) == 3
    names = {s.name for s in card.thesis.scenarios}
    assert names == {"BULL", "BASE", "BEAR"}
    total = sum(s.probability for s in card.thesis.scenarios)
    assert 0.95 <= total <= 1.05

    # Citations are data-only (no llm-interpretation leak)
    for c in card.citations:
        assert c.source_type in _VALID_SOURCE_TYPES

    # Catalysts: either populated OR explicit no_catalysts_reason
    if not card.thesis.catalysts:
        assert card.thesis.no_catalysts_reason
