"""extract_news_relations_for_ticker — News table → LLM → validate flow."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import News, Stock, StockRelation
from app.services.ontology.extract_news import (
    extract_news_relations_for_ticker,
)


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def generate_json(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._responses.pop(0) if self._responses else '{"relations":[]}'


@pytest.mark.asyncio
async def test_news_extracts_competitor_relation(db) -> None:
    a = Stock(ticker="EX9101", name="Alpha Inc", market="US", sector="Auto", tier=1)
    b = Stock(ticker="EX9102", name="Beta Inc", market="US", sector="Auto", tier=1)
    db.add_all([a, b])
    await db.flush()

    db.add(News(
        stock_id=a.id,
        title="EX9102 raises prices, EX9101 to benefit",
        source="reuters",
        url="https://example.com/n/1",
        content="A" * 200,
        published_at=datetime.now() - timedelta(days=1),
    ))
    await db.flush()

    llm = _FakeLLM([json.dumps({"relations": [{
        "from_ticker": "EX9102", "to_ticker": "EX9101",
        "relation_type": "competitor", "signal_direction": "inverse",
        "strength": 0.6, "confidence": 0.75,
        # rationale must contain both target Stock.name strings ("Alpha Inc",
        # "Beta Inc") — validator's defense-in-depth substring gate requires
        # to_target name evidence inside the rationale (length-padded test).
        "metadata": {
            "rationale": "Beta Inc price hike enables Alpha Inc to gain market share in mid-tier auto segment."
        },
    }]})])

    summary = await extract_news_relations_for_ticker(
        "EX9101",
        since=date.today() - timedelta(days=7),
        llm_adapter=llm,
        session=db,
    )

    assert summary["articles_seen"] == 1
    assert summary["upserted"] == 2  # forward + reciprocal (competitor symmetric)
    assert len(llm.calls) == 1

    rels = (
        await db.execute(
            select(StockRelation).where(StockRelation.source == "news")
        )
    ).scalars().all()
    assert len(rels) == 2
    # Both directions get inverse — competitor is symmetric.
    assert all(r.signal_direction == "inverse" for r in rels)
    assert all(r.relation_type == "competitor" for r in rels)


@pytest.mark.asyncio
async def test_news_skips_null_content_articles(db) -> None:
    s = Stock(ticker="EX9111", name="Solo", market="US", sector="IT", tier=1)
    db.add(s)
    await db.flush()
    db.add(News(
        stock_id=s.id, title="t", source="src", url="https://example.com/n/2",
        content=None, published_at=datetime.now() - timedelta(days=1),
    ))
    await db.flush()

    llm = _FakeLLM([])  # would fail-cycle if called
    summary = await extract_news_relations_for_ticker(
        "EX9111",
        since=date.today() - timedelta(days=7),
        llm_adapter=llm,
        session=db,
    )
    assert summary["articles_seen"] == 0
    assert llm.calls == []


@pytest.mark.asyncio
async def test_news_unknown_ticker_returns_error(db) -> None:
    llm = _FakeLLM([])
    summary = await extract_news_relations_for_ticker(
        "ZZZNONE", since=date.today() - timedelta(days=7),
        llm_adapter=llm, session=db,
    )
    assert "error" in summary
    assert llm.calls == []
