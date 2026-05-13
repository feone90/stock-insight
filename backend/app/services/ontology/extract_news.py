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
    skipped_short = 0
    skipped_no_focal_evidence = 0
    skipped_target_not_in_article = 0
    llm_returned_total = 0
    focal_token_low = ticker.lower()
    focal_name = stock.name or ticker
    focal_name_low = focal_name.lower()

    # Phase 1 — collect (article, llm_relations) per article + accumulate target
    # tickers so we can do ONE bulk name-lookup for the substring evidence gate.
    # 한국 기사는 "삼성전자" 같은 한글 이름으로만 쓰지 ticker 코드 ("005930") 는
    # 거의 안 쓴다. ticker substring 만 보면 KR 종목 전부 drop 됨.
    pending: list[tuple[News, list[ExtractedRelation], str, bool]] = []
    needed_tickers: set[str] = set()
    for art in articles:
        body = (art.content or "").strip()
        if len(body) < 50:
            skipped_short += 1
            continue
        haystack_low = f"{art.title}\n{body}".lower()
        focal_in_article = (
            focal_token_low in haystack_low
            or (focal_name_low and focal_name_low in haystack_low)
        )
        enriched = f"제목: {art.title}\n\n{body}"
        rels = await extract_relations(
            body=enriched,
            prompt_template=NEWS_COMPETITOR_PROMPT,
            source_url=art.url,
            adapter=llm_adapter,
            prompt_kwargs={
                "focal_ticker": ticker,
                "focal_name": focal_name,
            },
        )
        llm_returned_total += len(rels)
        if not focal_in_article:
            skipped_no_focal_evidence += len(rels)
            continue
        pending.append((art, rels, haystack_low, focal_in_article))
        for rel in rels:
            for tk in (rel.from_ticker, rel.to_ticker):
                if tk:
                    needed_tickers.add(tk.upper())

    # Phase 2 — bulk lookup target names from Stock table.
    ticker_to_name: dict[str, str] = {}
    if needed_tickers:
        rows = (
            await session.execute(
                select(Stock.ticker, Stock.name).where(Stock.ticker.in_(needed_tickers))
            )
        ).all()
        ticker_to_name = {t.upper(): (n or "") for t, n in rows}

    # Phase 3 — per-relation evidence gate (focal already verified; check OTHER side).
    for art, rels, haystack_low, _focal_in in pending:
        for rel in rels:
            # 시황성 type (peer/theme/macro/group) 은 news 출처 에선 거의 항상
            # "단순 같이 나옴" 신호다. sector_match 가 별도로 peer 깔아두니
            # news LLM 추출에선 사업 본질 type 만 통과시킨다.
            if rel.relation_type in {"peer", "theme", "macro", "group"}:
                skipped_no_focal_evidence += 1
                continue
            from_t = (rel.from_ticker or "").lower()
            to_t = (rel.to_ticker or "").lower()
            if focal_token_low not in (from_t, to_t):
                skipped_no_focal_evidence += 1
                continue
            other_ticker = to_t if from_t == focal_token_low else from_t
            other_name = ticker_to_name.get(other_ticker.upper(), "").lower()
            # Accept if EITHER target ticker OR target name appears in article.
            # KR 기사는 한글 이름 위주라 name match 가 실질 evidence.
            if (other_ticker and other_ticker in haystack_low) or (
                other_name and other_name in haystack_low
            ):
                relations.append(rel)
            else:
                skipped_target_not_in_article += 1

    summary = await validate_and_route(relations, source=_SOURCE, session=session)
    summary["ticker"] = ticker
    summary["articles_seen"] = len(articles)
    summary["articles_skipped_short"] = skipped_short
    summary["llm_relations_returned"] = llm_returned_total
    summary["evidence_dropped_no_focal"] = skipped_no_focal_evidence
    summary["evidence_dropped_target_missing"] = skipped_target_not_in_article
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
