"""ExtractedRelation / ExtractionBatch — Pydantic invariants."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.ontology.schemas import ExtractedRelation, ExtractionBatch


def test_minimal_valid_relation_uses_defaults() -> None:
    rel = ExtractedRelation.model_validate({
        "from_ticker": "005930",
        "to_ticker": "000660",
        "relation_type": "peer",
    })
    assert rel.signal_direction == "positive"
    assert rel.strength == 0.5
    assert rel.confidence == 0.5
    assert rel.extra_metadata == {}


def test_metadata_alias_accepted() -> None:
    """LLM emits `metadata`; Python attribute is `extra_metadata` (avoids
    SQLAlchemy reserved-name conflict)."""
    rel = ExtractedRelation.model_validate({
        "from_ticker": "AAPL",
        "to_ticker": "MSFT",
        "relation_type": "competitor",
        "metadata": {"value_usd": 1_000_000_000, "rationale": "rivalry"},
    })
    assert rel.extra_metadata == {"value_usd": 1_000_000_000, "rationale": "rivalry"}


def test_us_ticker_normalized_uppercase() -> None:
    rel = ExtractedRelation.model_validate({
        "from_ticker": "tsla",
        "to_ticker": "  aapl ",
        "relation_type": "competitor",
    })
    assert rel.from_ticker == "TSLA"
    assert rel.to_ticker == "AAPL"


def test_kr_six_digit_kept_as_is() -> None:
    rel = ExtractedRelation.model_validate({
        "from_ticker": "005930",
        "to_ticker": "000660",
        "relation_type": "peer",
    })
    assert rel.from_ticker == "005930"
    assert rel.to_ticker == "000660"


def test_invalid_confidence_raises() -> None:
    with pytest.raises(ValidationError):
        ExtractedRelation.model_validate({
            "from_ticker": "AAPL",
            "to_ticker": "MSFT",
            "relation_type": "peer",
            "confidence": 1.5,  # out of [0, 1]
        })


def test_invalid_relation_type_raises() -> None:
    with pytest.raises(ValidationError):
        ExtractedRelation.model_validate({
            "from_ticker": "AAPL",
            "to_ticker": "MSFT",
            "relation_type": "made_up_type",
        })


def test_extraction_batch_accepts_array_via_relations_key() -> None:
    batch = ExtractionBatch.model_validate({
        "relations": [
            {"from_ticker": "AAPL", "to_ticker": "MSFT", "relation_type": "peer"},
            {"from_ticker": "TSLA", "to_ticker": "F", "relation_type": "competitor"},
        ]
    })
    assert len(batch.relations) == 2
    assert {r.from_ticker for r in batch.relations} == {"AAPL", "TSLA"}
