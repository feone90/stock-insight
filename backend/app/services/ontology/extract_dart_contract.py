"""KR DART 주요사항보고서 (단일판매·공급계약체결 등) LLM RAG (Codex F, 2026-05-14).

Per KR ticker, use dartlab `Company.disclosure(keyword=...)` to list contract
filings, fetch the document body via DART OpenDART REST `/api/document.xml`
(ZIP archive), and run LLM RAG to extract supplier/customer relations.

P1.6 v2 plan 에 placeholder 만 있던 `dart_contract` source — 이번 phase 에서
실 구현. SEC 8-K extractor 와 동일 흐름:

  dartlab disclosure(keyword=...) → contract filings list
  → DART REST document.xml → unzip → text
  → LLM RAG with DART_CONTRACT_PROMPT
  → validate_and_route to stock_relations / candidates.

project_ontology_codex_review_2026_05_14 §우선순위 F.
"""
from __future__ import annotations

import asyncio
import logging
import re
import zipfile
from datetime import date  # noqa: F401  (kept for API parity with extract_sec)
from io import BytesIO

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import Stock
from app.services.ontology.extractor import extract_relations
from app.services.ontology.prompts import DART_CONTRACT_PROMPT
from app.services.ontology.schemas import ExtractedRelation
from app.services.ontology.validator import validate_and_route

logger = logging.getLogger(__name__)

_SOURCE = "dart_contract"
_DEFAULT_WINDOW_DAYS = 365
_MAX_FILINGS_PER_TICKER = 5  # KR 단일종목 1년 contract 공시 보통 1-5건
_DART_DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
_DART_TIMEOUT = 20.0
_BODY_MAX_CHARS = 30_000  # extractor 가 다시 12K cut (cost cap)

# 주요사항보고서 contract 키워드. 단일판매·공급계약체결 + 양수도 + 출자.
_CONTRACT_KEYWORDS = ["공급계약", "단일판매", "양수도"]

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


async def _fetch_document_body(rcept_no: str) -> str | None:
    """DART OpenDART /api/document.xml 호출 → zip → text.

    DART body 는 EUC-KR/CP949 흔함. UTF-8 fallback 으로 디코드. HTML tag
    strip 후 whitespace 정규화. cap _BODY_MAX_CHARS.
    """
    if not settings.dart_api_key:
        logger.warning("DART_API_KEY 미설정 — contract body fetch skip")
        return None
    params = {"crtfc_key": settings.dart_api_key, "rcept_no": rcept_no}
    try:
        async with httpx.AsyncClient(timeout=_DART_TIMEOUT) as client:
            resp = await client.get(_DART_DOC_URL, params=params)
            resp.raise_for_status()
            zip_bytes = resp.content
    except Exception as e:  # noqa: BLE001
        logger.warning("DART document fetch failed for %s: %s", rcept_no, e)
        return None
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            target = next(
                (n for n in names if n.lower().endswith((".xml", ".htm", ".html"))),
                names[0] if names else None,
            )
            if not target:
                return None
            with zf.open(target) as f:
                raw = f.read()
    except Exception as e:  # noqa: BLE001 — zipfile.BadZipFile 등 포괄
        logger.warning("DART zip unzip failed for %s: %s", rcept_no, e)
        return None

    text: str | None = None
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    text = _HTML_TAG.sub(" ", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()[:_BODY_MAX_CHARS]


def _dartlab_contract_filings(ticker: str, days: int) -> list[dict]:  # pragma: no cover
    """dartlab `Company.disclosure(keyword=...)` 로 contract filings list.

    여러 키워드 union + rcept_no dedup. polars DataFrame → dict list.
    """
    try:
        import dartlab
    except ImportError:
        return []
    try:
        c = dartlab.Company(ticker)
    except Exception as e:  # noqa: BLE001
        logger.warning("dartlab Company(%s) failed: %s", ticker, e)
        return []

    seen: dict[str, dict] = {}
    for kw in _CONTRACT_KEYWORDS:
        try:
            df = c.disclosure(days=days, keyword=kw)
        except Exception as e:  # noqa: BLE001
            logger.info(
                "dartlab disclosure(%s, keyword=%s) fail: %s", ticker, kw, e
            )
            continue
        if df is None:
            continue
        try:
            is_empty = df.is_empty() if hasattr(df, "is_empty") else len(df) == 0
        except Exception:  # noqa: BLE001
            is_empty = False
        if is_empty:
            continue
        try:
            rows = df.to_dicts()
        except Exception:  # noqa: BLE001
            continue
        for r in rows:
            rcept_no = r.get("rcept_no")
            if not rcept_no:
                continue
            if rcept_no in seen:
                continue
            seen[rcept_no] = r
    out = list(seen.values())
    out.sort(key=lambda r: r.get("rcept_dt", ""), reverse=True)
    return out


async def extract_dart_contracts(
    ticker: str,
    *,
    days: int = _DEFAULT_WINDOW_DAYS,
    llm_adapter=None,
    session: AsyncSession | None = None,
) -> dict:
    """KR ticker 의 최근 contract 공시 LLM RAG."""
    filings = await asyncio.to_thread(_dartlab_contract_filings, ticker, days)
    if not filings:
        return {
            "ticker": ticker,
            "filings_seen": 0,
            "added": 0,
            "candidate_count": 0,
            "skipped": 0,
        }

    relations: list[ExtractedRelation] = []
    for f in filings[:_MAX_FILINGS_PER_TICKER]:
        rcept_no = f.get("rcept_no")
        if not rcept_no:
            continue
        body = await _fetch_document_body(str(rcept_no))
        if not body or len(body) < 200:
            continue
        # DART 사용자 열람 URL (rcpNo param)
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        rels = await extract_relations(
            body=body,
            prompt_template=DART_CONTRACT_PROMPT,
            source_url=url,
            adapter=llm_adapter,
        )
        relations.extend(rels)

    summary = await validate_and_route(relations, source=_SOURCE, session=session)
    summary["ticker"] = ticker
    summary["filings_seen"] = len(filings)
    return summary


async def extract_dart_contracts_for_universe(
    *,
    days: int = _DEFAULT_WINDOW_DAYS,
    limit: int | None = None,
    sleep_between: float = 0.5,
) -> list[dict]:
    """KR Tier 1+2 universe sequential. dartlab + DART REST rate limits 고려.

    dartlab Company 객체 자체가 internal cache 있고 우리도 ResultCache 가
    있어 repeated call 부담은 적음. DART REST `/document.xml` 는 무료 키 기준
    분당 ~100 호출 안전권 (실제 한계 documented X) — `sleep_between=0.5` 면
    분당 ~120, contract 공시 평균 ticker 당 1-2건이라 LLM cost 도 통제됨.
    """
    async with async_session() as session:
        result = await session.execute(
            select(Stock.ticker).where(
                Stock.market.in_(("KOSPI", "KOSDAQ")),
                Stock.tier <= 2,
                Stock.is_delisted.is_(False),
            )
        )
        tickers = [row.ticker for row in result.all()]
    if limit is not None:
        tickers = tickers[:limit]

    summaries: list[dict] = []
    for ticker in tickers:
        summary = await extract_dart_contracts(ticker, days=days)
        summaries.append(summary)
        if sleep_between:
            await asyncio.sleep(sleep_between)
    return summaries
