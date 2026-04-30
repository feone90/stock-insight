"""extract_relations — JSON parse, retry, response shape tolerance."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.services.ontology import extractor as extractor_module
from app.services.ontology.extractor import extract_relations
from app.services.ontology.prompts import DART_CONTRACT_PROMPT


class _FakeAdapter:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def generate_json(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_extracts_clean_json_array() -> None:
    payload = json.dumps([
        {
            "from_ticker": "005930", "to_ticker": "000660",
            "relation_type": "contract_supplier",
            "signal_direction": "positive", "strength": 0.8, "confidence": 0.9,
        }
    ])
    adapter = _FakeAdapter([payload])

    rels = await extract_relations(
        body="A" * 100, prompt_template=DART_CONTRACT_PROMPT, adapter=adapter,
    )
    assert len(rels) == 1
    assert rels[0].from_ticker == "005930"
    assert rels[0].confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_tolerates_relations_wrapper_object() -> None:
    payload = json.dumps({
        "relations": [
            {"from_ticker": "AAPL", "to_ticker": "MSFT", "relation_type": "peer",
             "strength": 0.5, "confidence": 0.6}
        ]
    })
    adapter = _FakeAdapter([payload])
    rels = await extract_relations(body="A" * 100, prompt_template="ignore {body}", adapter=adapter)
    assert rels[0].from_ticker == "AAPL"


@pytest.mark.asyncio
async def test_strips_code_fence() -> None:
    raw = '```json\n[{"from_ticker": "TSLA", "to_ticker": "F", "relation_type": "competitor", "strength": 0.7, "confidence": 0.7}]\n```'
    adapter = _FakeAdapter([raw])
    rels = await extract_relations(body="A" * 100, prompt_template="ignore {body}", adapter=adapter)
    assert rels[0].relation_type == "competitor"


@pytest.mark.asyncio
async def test_retries_once_on_invalid_json_then_succeeds() -> None:
    bad = "not json at all"
    good = json.dumps([{
        "from_ticker": "AAPL", "to_ticker": "MSFT", "relation_type": "peer",
        "strength": 0.5, "confidence": 0.6,
    }])
    adapter = _FakeAdapter([bad, good])

    rels = await extract_relations(body="A" * 100, prompt_template="ignore {body}", adapter=adapter)
    assert len(rels) == 1
    assert len(adapter.calls) == 2  # one retry consumed


@pytest.mark.asyncio
async def test_retries_once_on_validation_error_then_gives_up() -> None:
    invalid = json.dumps([{
        "from_ticker": "AAPL", "to_ticker": "MSFT", "relation_type": "peer",
        "confidence": 5.0,  # out of range — both attempts fail
    }])
    adapter = _FakeAdapter([invalid, invalid])

    rels = await extract_relations(body="A" * 100, prompt_template="ignore {body}", adapter=adapter)
    assert rels == []
    assert len(adapter.calls) == 2  # used the retry


@pytest.mark.asyncio
async def test_short_body_returns_empty_without_calling_llm() -> None:
    adapter = _FakeAdapter([])  # would IndexError if called
    rels = await extract_relations(body="too short", prompt_template="ignore {body}", adapter=adapter)
    assert rels == []
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_source_url_injected_into_metadata() -> None:
    payload = json.dumps([{
        "from_ticker": "AAPL", "to_ticker": "MSFT", "relation_type": "peer",
        "strength": 0.5, "confidence": 0.7,
    }])
    adapter = _FakeAdapter([payload])
    rels = await extract_relations(
        body="A" * 100,
        prompt_template="ignore {body}",
        source_url="https://example.com/filing/123",
        adapter=adapter,
    )
    assert rels[0].extra_metadata["source_url"] == "https://example.com/filing/123"
