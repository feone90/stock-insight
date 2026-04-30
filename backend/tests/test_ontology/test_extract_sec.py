"""extract_sec_contracts — 8-K filing → LLM → validate flow."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models import RelationCandidate, Stock, StockRelation
from app.services.ontology.extract_sec import (
    extract_sec_contracts,
    extract_sec_contracts_for_universe,
)


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def generate_json(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._responses.pop(0) if self._responses else "[]"


def _fake_sec_adapter(filings: list[dict], body: str = "BODY" * 100):
    adapter = AsyncMock()
    adapter.fetch_8k_filings = AsyncMock(return_value=filings)
    adapter.fetch_filing_body = AsyncMock(return_value=body)
    return adapter


@pytest.mark.asyncio
async def test_one_filing_extracts_and_persists_relation(db) -> None:
    a = Stock(ticker="EX0001", name="Example A", market="US", sector="Auto", tier=1)
    b = Stock(ticker="EX0002", name="Example B", market="US", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    sec = _fake_sec_adapter([
        {
            "cik": "1318605",
            "accession": "0001104659-25-087862",
            "filing_date": "2025-09-05",
            "primary_document": "tm2525337d1_8k.htm",
            "items": "1.01,9.01",
        }
    ])
    llm = _FakeLLM([json.dumps([
        {"from_ticker": "EX0001", "to_ticker": "EX0002",
         "relation_type": "contract_supplier",
         "signal_direction": "positive", "strength": 0.7, "confidence": 0.85,
         "metadata": {"value_usd": 1_000_000_000}},
    ])])

    summary = await extract_sec_contracts(
        "EX0001", since=date(2025, 1, 1), adapter=sec, llm_adapter=llm, session=db
    )

    assert summary["filings_seen"] == 1
    assert summary["upserted"] == 2  # forward + reciprocal
    assert summary["buffered"] == 0

    rel = (
        await db.execute(
            select(StockRelation).where(
                StockRelation.from_stock_id == a.id,
                StockRelation.source == "sec_8k",
            )
        )
    ).scalar_one()
    assert rel.to_target == "EX0002"
    assert rel.confidence == pytest.approx(0.85)
    assert rel.extra_metadata is not None
    assert rel.extra_metadata.get("value_usd") == 1_000_000_000
    assert rel.extra_metadata.get("source_url", "").startswith(
        "https://www.sec.gov/Archives/edgar/data/1318605/"
    )


@pytest.mark.asyncio
async def test_no_filings_skips_llm(db) -> None:
    sec = _fake_sec_adapter([])
    llm = _FakeLLM([])
    summary = await extract_sec_contracts(
        "AAPL", since=date(2025, 1, 1), adapter=sec, llm_adapter=llm, session=db
    )
    assert summary["filings_seen"] == 0
    assert summary["received"] == 0
    assert llm.calls == []


@pytest.mark.asyncio
async def test_body_fetch_failure_continues_to_next_filing(db) -> None:
    a = Stock(ticker="NVDA", name="Nvidia", market="US", sector="IT", tier=1)
    b = Stock(ticker="AMD", name="AMD", market="US", sector="IT", tier=1)
    db.add_all([a, b])
    await db.flush()

    sec = AsyncMock()
    sec.fetch_8k_filings = AsyncMock(return_value=[
        {"cik": "1045810", "accession": "ACC1", "filing_date": "2025-06-01",
         "primary_document": "ok.htm", "items": "1.01"},
        {"cik": "1045810", "accession": "ACC2", "filing_date": "2025-07-01",
         "primary_document": "broken.htm", "items": "1.01"},
    ])

    async def _body_side_effect(*, cik, accession, primary_document):
        if accession == "ACC2":
            raise RuntimeError("network error")
        return "GOOD BODY " * 50

    sec.fetch_filing_body = AsyncMock(side_effect=_body_side_effect)

    llm = _FakeLLM([
        json.dumps([{
            "from_ticker": "NVDA", "to_ticker": "AMD",
            "relation_type": "contract_supplier",
            "strength": 0.6, "confidence": 0.8,
        }]),
    ])

    summary = await extract_sec_contracts(
        "NVDA", since=date(2025, 1, 1), adapter=sec, llm_adapter=llm, session=db
    )
    assert summary["filings_seen"] == 2
    assert summary["upserted"] == 2  # forward + reciprocal
    assert len(llm.calls) == 1  # only the successful body went to LLM


@pytest.mark.asyncio
async def test_extracted_ticker_outside_universe_buffered(db) -> None:
    a = Stock(ticker="EX9001", name="Example", market="US", sector="Auto", tier=1)
    db.add(a)
    await db.flush()

    sec = _fake_sec_adapter([{
        "cik": "1318605", "accession": "ACC", "filing_date": "2025-06-01",
        "primary_document": "doc.htm", "items": "1.01",
    }])
    # LLM extracts a counterparty NOT in our universe → relation_candidates buffer
    llm = _FakeLLM([json.dumps([{
        "from_ticker": "EX9001", "to_ticker": "PRIVATECO",
        "relation_type": "contract_customer",
        "strength": 0.5, "confidence": 0.7,
    }])])

    summary = await extract_sec_contracts(
        "EX9001", since=date(2025, 1, 1), adapter=sec, llm_adapter=llm, session=db
    )

    assert summary["upserted"] == 0
    assert summary["buffered"] == 1
    cand = (
        await db.execute(
            select(RelationCandidate).where(RelationCandidate.from_ticker == "EX9001")
        )
    ).scalar_one()
    assert cand.to_ticker == "PRIVATECO"
    assert cand.source == "sec_8k"
