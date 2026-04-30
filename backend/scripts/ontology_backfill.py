"""Ontology relation extraction — manual backfill entry (P1.6 v1 / v2).

Runs LLM RAG over recent SEC 8-K filings (or future: DART contracts, news)
and routes the extracted relations to `stock_relations` / `relation_candidates`
via the validator.

LLM 비용이 발생한다 — `--limit` / `--ticker`로 범위를 좁힌 manual run을
권장. nightly cron (별도 PR)이 있어서 운영은 거기서 점진 누적.

Usage::

    # SEC 8-K, single ticker (smoke)
    uv run python -m scripts.ontology_backfill --source sec --ticker TSLA \
        --since 2025-01-01

    # SEC 8-K, universe-wide capped (~$1)
    uv run python -m scripts.ontology_backfill --source sec --since 2026-04-23 \
        --limit 50

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §12
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


async def run_sec(
    *, since: date, ticker: str | None, limit: int | None, sleep: float
) -> None:
    from app.services.ontology import (
        extract_sec_contracts,
        extract_sec_contracts_for_universe,
    )

    if ticker:
        summary = await extract_sec_contracts(ticker, since=since)
        logger.info("sec backfill ticker=%s: %s", ticker, summary)
        print(summary)
        return

    summaries = await extract_sec_contracts_for_universe(
        since=since, limit=limit, sleep_between=sleep
    )
    total_upserted = sum(s.get("upserted", 0) for s in summaries)
    total_buffered = sum(s.get("buffered", 0) for s in summaries)
    total_filings = sum(s.get("filings_seen", 0) for s in summaries)
    print(
        f"sec backfill: tickers={len(summaries)} filings={total_filings} "
        f"upserted={total_upserted} buffered={total_buffered}"
    )


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ontology relation backfill (P1.6).")
    parser.add_argument(
        "--source", choices=["sec"], default="sec",
        help="Extraction source. v1 (DART) and v3 (news) are separate follow-ups.",
    )
    parser.add_argument(
        "--since", type=_parse_date, required=True,
        help="ISO date — only filings dated >= since are processed.",
    )
    parser.add_argument(
        "--ticker", help="Run for one ticker (skip universe loop). Smoke / debugging.",
    )
    parser.add_argument(
        "--limit", type=int,
        help="Cap universe loop length. Strongly recommended for cost control.",
    )
    parser.add_argument(
        "--sleep", type=float, default=0.0,
        help="Seconds to pause between tickers (SEC rate-limit pacing).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv()

    if args.source == "sec":
        asyncio.run(
            run_sec(
                since=args.since,
                ticker=args.ticker,
                limit=args.limit,
                sleep=args.sleep,
            )
        )


if __name__ == "__main__":
    main()
