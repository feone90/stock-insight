"""SEC 10-K Item 1A. Risk Factors LLM RAG (Codex review G, 2026-05-14).

Per US ticker, fetch the most recent 10-K filing, slice out the "Item 1A.
Risk Factors" section, and run LLM RAG to extract relations with other
publicly-listed companies (customer / supplier / competitor / regulatory).

Why this matters (project_ontology_codex_review_2026_05_14 §우선순위 G):
- 8-K extractor (`extract_sec.py`) covers Item 1.01 contracts only — episodic.
- News RAG (`extract_news.py`) covers a 14-day window — misses long-running
  structural ties.
- 10-K Risk Factors is where companies *must* disclose customer concentration,
  sole-supplier dependence, and key competitors. ASML-style capex tie-ins live
  here and nowhere else in our pipeline.

Same flow as `extract_sec.py`:
  SEC adapter → list 10-K filings (since N days)
  → fetch primary body
  → extract Item 1A section (regex slice — 10-K body is huge)
  → LLM RAG with `TEN_K_RISK_PROMPT` (focal_ticker / focal_name injected)
  → validate_and_route to stock_relations / candidates.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Stock
from app.services.external_data_adapters.sec_edgar_adapter import SecEdgarAdapter
from app.services.ontology.extract_sec import _archives_url
from app.services.ontology.extractor import extract_relations
from app.services.ontology.prompts import TEN_K_RISK_PROMPT
from app.services.ontology.schemas import ExtractedRelation
from app.services.ontology.validator import validate_and_route

logger = logging.getLogger(__name__)

_SOURCE = "sec_10k_risk"
_DEFAULT_WINDOW_DAYS = 730   # 2년 — 가장 최근 annual 1건 잡기에 여유
_MAX_FILINGS_PER_TICKER = 1  # 가장 최근 annual 만 LLM 처리 (cost)
_ITEM_1A_MAX_CHARS = 50_000  # extractor 가 다시 12k로 cut — 본문 cap 은 logging 의미


# 10-K 본문은 HTML/inline-XBRL. "Item 1A. Risk Factors" 부터 "Item 1B" 또는
# "Item 2" 까지 cut. 변형 흡수: "ITEM 1A.", "Item 1A:", "Item 1A —" 등.
_ITEM_1A_OPEN = re.compile(
    r"item\s*1\s*a[\s.:\-—]*risk\s+factors", re.IGNORECASE
)
_ITEM_1A_CLOSE = re.compile(r"item\s*1\s*b|item\s*2[.\s]", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _extract_item_1a(body: str) -> str:
    """10-K 본문에서 Item 1A. Risk Factors 텍스트만 추출. HTML strip + 영역 cut."""
    if not body:
        return ""
    text = _HTML_TAG.sub(" ", body)
    text = _WHITESPACE.sub(" ", text)
    open_m = _ITEM_1A_OPEN.search(text)
    if not open_m:
        # Item 1A 헤더 못 찾음 — 첫 _ITEM_1A_MAX_CHARS 만 반환 (fallback)
        return text[:_ITEM_1A_MAX_CHARS]
    start = open_m.end()
    close_m = _ITEM_1A_CLOSE.search(text, pos=start)
    end = close_m.start() if close_m else min(len(text), start + _ITEM_1A_MAX_CHARS)
    section = text[start:end].strip()
    return section[:_ITEM_1A_MAX_CHARS]


async def extract_10k_risk(
    ticker: str,
    *,
    since: date | None = None,
    adapter: SecEdgarAdapter | None = None,
    llm_adapter=None,
    session: AsyncSession | None = None,
) -> dict:
    """Extract 10-K Item 1A relations for one US ticker.

    Returns validator summary + filings_seen count + ticker. Idempotent.
    """
    if since is None:
        since = date.today() - timedelta(days=_DEFAULT_WINDOW_DAYS)

    sec = adapter or SecEdgarAdapter()
    try:
        filings = await sec.fetch_10k_filings(ticker, since=since)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_10k_filings(%s) failed: %s", ticker, e)
        return {"ticker": ticker, "filings_seen": 0, "error": str(e)}

    if not filings:
        return {
            "ticker": ticker, "filings_seen": 0, "added": 0,
            "candidate_count": 0, "skipped": 0,
        }

    # focal 회사명 (prompt 변수) — DB에서 1회만 조회.
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
    focal_name = stock.name if stock else ticker

    relations: list[ExtractedRelation] = []
    # 가장 최근 1건만 LLM (annual, older 10-K 정보 stale + cost 절감)
    for f in filings[:_MAX_FILINGS_PER_TICKER]:
        try:
            body = await sec.fetch_filing_body(
                cik=f["cik"],
                accession=f["accession"],
                primary_document=f["primary_document"],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("10-K body fetch failed %s/%s: %s", ticker, f["accession"], e)
            continue
        if not body:
            continue
        section = _extract_item_1a(body)
        if len(section) < 200:
            logger.info("10-K %s Item 1A short or missing (%d chars)", ticker, len(section))
            continue
        url = _archives_url(f["cik"], f["accession"], f["primary_document"])
        rels = await extract_relations(
            body=section,
            prompt_template=TEN_K_RISK_PROMPT,
            source_url=url,
            adapter=llm_adapter,
            prompt_kwargs={"focal_ticker": ticker, "focal_name": focal_name},
        )
        relations.extend(rels)

    summary = await validate_and_route(relations, source=_SOURCE, session=session)
    summary["ticker"] = ticker
    summary["filings_seen"] = len(filings)
    return summary


async def extract_10k_risk_for_universe(
    *,
    since: date | None = None,
    limit: int | None = None,
    sleep_between: float = 0.5,
) -> list[dict]:
    """Run 10-K extractor across US Tier 1+2 universe.

    Sequential — SEC 10 req/s limit + per-ticker LLM cost. `limit` caps
    tickers per run (manual backfill), `sleep_between` paces. Daily/weekly
    cron 트리거에 적합 — 10-K 갱신은 분기에 1번뿐이라 자주 돌 필요 없음.
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
        summary = await extract_10k_risk(ticker, since=since, adapter=sec)
        summaries.append(summary)
        if sleep_between:
            await asyncio.sleep(sleep_between)
    return summaries
