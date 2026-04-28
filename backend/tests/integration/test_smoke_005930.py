"""Real-LLM smoke test for v2 analyst engine.

Run only with:
    cd backend && uv run python -m pytest -m smoke -v

Costs ~$0.5–1.2 per run. Requires:
    AZURE_OPENAI_*, TAVILY_API_KEY in .env
    DB seeded with 005930 (삼성전자)
"""
import pytest

from app.config import settings
from app.schemas.card import StockCard
from app.services.analyst.engine import analyze


_FORBIDDEN_WORDS = [
    "워렌버핏",
    "Buffett",
    "전문가급",
    "강력 매수",
    "확실한 수익",
    "유망주",
]

_VALID_SOURCE_TYPES = {
    "db",
    "market_data",
    "news",
    "disclosure",
    "web",
    "curated_relation",
}


@pytest.mark.smoke
@pytest.mark.skipif(
    not settings.tavily_api_key,
    reason="TAVILY_API_KEY not configured in .env; smoke test requires real keys",
)
@pytest.mark.asyncio
async def test_smoke_analyze_005930_produces_valid_card():
    """End-to-end: research → synthesize → persist for 삼성전자."""
    card = await analyze("005930")
    assert isinstance(card, StockCard)
    assert card.ticker == "005930"

    # Persona traceability — server-controlled
    assert card.persona_version == "analyst_v1"
    assert card.schema_version == "v2"

    # Evidence balance — persona contract
    assert len(card.thesis.supports) >= 3, "supports must be ≥3"
    assert len(card.thesis.opposes) >= 2, "opposes must be ≥2"
    assert len(card.thesis.scenarios) == 3, "exactly BULL/BASE/BEAR"
    names = {s.name for s in card.thesis.scenarios}
    assert names == {"BULL", "BASE", "BEAR"}

    # Probability sums roughly to 1
    total = sum(s.probability for s in card.thesis.scenarios)
    assert 0.95 <= total <= 1.05, f"scenario probabilities should sum ~1.0, got {total}"

    # Citations are data-only (no llm-interpretation leak)
    for c in card.citations:
        assert c.source_type in _VALID_SOURCE_TYPES, (
            f"forbidden source_type: {c.source_type}"
        )

    # Catalysts: either populated OR explicit no_catalysts_reason
    if not card.thesis.catalysts:
        assert card.thesis.no_catalysts_reason, (
            "empty catalysts must come with no_catalysts_reason"
        )

    # Forbidden marketing words must NOT appear in user-facing text
    blob = (
        card.glance.one_line
        + " "
        + card.thesis.core_thesis
        + " "
        + card.decision.note
    )
    for forbidden in _FORBIDDEN_WORDS:
        assert forbidden not in blob, f"forbidden word leaked into UI: {forbidden}"
