"""News-driven relation extraction (P1.6 v3).

Pulls recent News rows (content present) for each universe ticker, runs the
competitor / inverse-signal LLM prompt, and routes results via the validator.

News bodies are short (often < 2K chars) so token cost stays low. Per plan
§8 estimate: ~$0.015/day at 100 articles/day. We further bound cost via
`limit` ticker cap and a per-ticker `articles_per_run` cap.

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6.4.1
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import News, Stock
from app.services.ontology.extractor import extract_relations
from app.services.ontology.prompts import NEWS_COMPETITOR_PROMPT
from app.services.ontology.schemas import ExtractedRelation
from app.services.ontology.validator import validate_and_route

logger = logging.getLogger(__name__)

_SOURCE = "news"
_DEFAULT_ARTICLES_PER_RUN = 5  # most informative recent articles per ticker


async def extract_news_relations_for_ticker(
    ticker: str,
    *,
    since: date,
    articles_per_run: int = _DEFAULT_ARTICLES_PER_RUN,
    llm_adapter=None,
    session: AsyncSession | None = None,
) -> dict:
    """Per-ticker news relation extraction. Pull at most `articles_per_run`
    most-recent articles with non-null content, run LLM, validate.
    """
    if session is not None:
        return await _run_for_ticker(
            session, ticker, since, articles_per_run, llm_adapter
        )
    async with async_session() as own:
        summary = await _run_for_ticker(
            own, ticker, since, articles_per_run, llm_adapter
        )
        await own.commit()
        return summary


async def _run_for_ticker(
    session: AsyncSession,
    ticker: str,
    since: date,
    articles_per_run: int,
    llm_adapter,
) -> dict:
    stock = (
        await session.execute(select(Stock).where(Stock.ticker == ticker))
    ).scalar_one_or_none()
    if stock is None:
        return {"ticker": ticker, "articles_seen": 0, "error": "ticker not in DB"}

    since_dt = datetime.combine(since, time.min)
    articles = (
        await session.execute(
            select(News)
            .where(
                News.stock_id == stock.id,
                News.published_at >= since_dt,
                News.content.isnot(None),
            )
            .order_by(News.published_at.desc())
            .limit(articles_per_run)
        )
    ).scalars().all()

    relations: list[ExtractedRelation] = []
    for art in articles:
        body = (art.content or "").strip()
        if len(body) < 100:
            continue
        rels = await extract_relations(
            body=body,
            prompt_template=NEWS_COMPETITOR_PROMPT,
            source_url=art.url,
            adapter=llm_adapter,
        )
        relations.extend(rels)

    summary = await validate_and_route(relations, source=_SOURCE, session=session)
    summary["ticker"] = ticker
    summary["articles_seen"] = len(articles)
    return summary


async def extract_news_relations_for_universe(
    *,
    since: date,
    limit: int | None = None,
    articles_per_run: int = _DEFAULT_ARTICLES_PER_RUN,
    sleep_between: float = 0.0,
) -> list[dict]:
    """Loop the universe (Tier 1+2, not delisted). `limit` caps per-run cost.

    Universe order is by ticker — deterministic. Future: prefer tickers
    with more recent News rows so each run touches fresh content.
    """
    async with async_session() as session:
        result = await session.execute(
            select(Stock.ticker).where(
                Stock.tier <= 2,
                Stock.is_delisted.is_(False),
            ).order_by(Stock.ticker)
        )
        tickers = [row.ticker for row in result.all()]
    if limit is not None:
        tickers = tickers[:limit]

    summaries: list[dict] = []
    for ticker in tickers:
        summary = await extract_news_relations_for_ticker(
            ticker, since=since, articles_per_run=articles_per_run
        )
        summaries.append(summary)
        if sleep_between:
            await asyncio.sleep(sleep_between)
    return summaries
