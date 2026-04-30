"""SEC 8-K Item 1.01 contract extraction (P1.6 v2).

Per US ticker, fetch 8-K filings whose `items` include "1.01" (Material Definitive
Agreement), pull each filing's primary HTML, run LLM RAG, and route the result
to `stock_relations` or `relation_candidates` via `validator.validate_and_route`.

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6.3
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Stock
from app.services.external_data_adapters.sec_edgar_adapter import (
    SEC_ARCHIVES_BASE,
    SecEdgarAdapter,
)
from app.services.ontology.extractor import extract_relations
from app.services.ontology.prompts import SEC_8K_CONTRACT_PROMPT
from app.services.ontology.schemas import ExtractedRelation
from app.services.ontology.validator import validate_and_route

logger = logging.getLogger(__name__)

_SOURCE = "sec_8k"


async def extract_sec_contracts(
    ticker: str,
    *,
    since: date,
    adapter: SecEdgarAdapter | None = None,
    llm_adapter=None,
    session: AsyncSession | None = None,
) -> dict:
    """Extract 8-K Item 1.01 contracts for one ticker.

    `since` is inclusive (filing_date >= since).
    Returns the validator summary plus a `filings_seen` count.
    """
    sec = adapter or SecEdgarAdapter()
    try:
        filings = await sec.fetch_8k_filings(ticker, since=since, item_code="1.01")
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_8k_filings(%s) failed: %s", ticker, e)
        return {"ticker": ticker, "filings_seen": 0, "error": str(e)}

    relations: list[ExtractedRelation] = []
    for f in filings:
        try:
            body = await sec.fetch_filing_body(
                cik=f["cik"],
                accession=f["accession"],
                primary_document=f["primary_document"],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("fetch_filing_body(%s/%s) failed: %s", ticker, f["accession"], e)
            continue
        if not body:
            continue
        url = _archives_url(f["cik"], f["accession"], f["primary_document"])
        rels = await extract_relations(
            body=body,
            prompt_template=SEC_8K_CONTRACT_PROMPT,
            source_url=url,
            adapter=llm_adapter,
        )
        relations.extend(rels)

    summary = await validate_and_route(relations, source=_SOURCE, session=session)
    summary["ticker"] = ticker
    summary["filings_seen"] = len(filings)
    return summary


async def extract_sec_contracts_for_universe(
    *,
    since: date,
    limit: int | None = None,
    sleep_between: float = 0.0,
) -> list[dict]:
    """Run the extractor across the US Tier 1+2 universe.

    Sequential — SEC's 10 req/s limit + LLM cost containment. `limit` caps
    tickers per run (manual backfill) and `sleep_between` paces the loop.
    """
    async with async_session() as session:
        result = await session.execute(
            select(Stock.ticker).where(
                Stock.market == "US",
                Stock.tier <= 2,
                Stock.is_delisted.is_(False),
            )
        )
        tickers = [row.ticker for row in result.all()]
    if limit is not None:
        tickers = tickers[:limit]

    sec = SecEdgarAdapter()
    summaries: list[dict] = []
    for ticker in tickers:
        summary = await extract_sec_contracts(ticker, since=since, adapter=sec)
        summaries.append(summary)
        if sleep_between:
            await asyncio.sleep(sleep_between)
    return summaries


def _archives_url(cik: str, accession: str, primary_doc: str) -> str:
    cik_int = str(int(cik))
    acc_no_dashes = accession.replace("-", "")
    return f"{SEC_ARCHIVES_BASE}/{cik_int}/{acc_no_dashes}/{primary_doc}"
