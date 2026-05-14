"""SEC EDGAR adapter — US primary (rawFinance + sector + fiscal_year_end).

httpx 직접 호출. SEC EDGAR public API는 무료 + API key 불필요. SEC 의무는
identifying User-Agent 헤더 (env-driven via SEC_USER_AGENT).

Spec §6.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.services.external_data_adapters.base import (
    ExternalAdapter,
    FinancialSeries,
    IdentityFacts,
    SectorInfo,
)

__all__ = ["SecEdgarAdapter"]
from app.services.external_data_adapters.cache import ResultCache
from app.services.external_data_adapters.constants import (
    SIC_MAPPING_HIT_CONFIDENCE,
    SIC_MAPPING_MISS_CONFIDENCE,
)

logger = logging.getLogger(__name__)

SEC_DATA_BASE = "https://data.sec.gov"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_GICS_PATH = _DATA_DIR / "sic_to_gics.json"
_TICKER_CACHE_PATH = _DATA_DIR / "sec_company_tickers.json"


def _user_agent() -> str:
    """SEC 의무: 요청자 식별 가능한 User-Agent. env에서만 읽음."""
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError(
            "SEC_USER_AGENT env not set — see backend/.env.example"
        )
    return ua


class SecEdgarAdapter(ExternalAdapter):
    """US primary. Direct httpx — no SDK, no MCP."""

    def __init__(
        self,
        cache: ResultCache | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._cache = cache or ResultCache()
        self._injected_client = client  # tests inject MockTransport-backed client
        self._client: httpx.AsyncClient | None = None
        self._gics_map: dict[str, dict] | None = None
        self._ticker_cik_map: dict[str, str] | None = None
        # SEC documents 10 req/sec; we stay well under but cap concurrency anyway.
        self._sem = asyncio.Semaphore(8)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": _user_agent()},
                timeout=10.0,
            )
        return self._client

    async def fetch_identity(self, ticker: str) -> IdentityFacts:
        cik = await self._ticker_to_cik(ticker)
        sub = await self._fetch_submissions(cik)
        raw_fye = sub.get("fiscalYearEnd")
        fiscal_year_end: str | None = None
        if isinstance(raw_fye, str) and len(raw_fye) == 4 and raw_fye.isdigit():
            fiscal_year_end = f"{raw_fye[:2]}-{raw_fye[2:]}"
        return IdentityFacts(
            ticker=ticker.upper(),
            name=sub.get("name") or ticker.upper(),
            market="US",
            currency="USD",
            fiscal_year_end=fiscal_year_end,
            cik=cik,
            corp_code=None,
            fetched_at=datetime.now(timezone.utc),
            source="sec_edgar",
        )

    async def fetch_company_facts(self, cik: str) -> dict:
        url = f"{SEC_DATA_BASE}/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
        client = await self._get_client()
        async with self._sem:
            r = await _retry_get(client, url)
        return r.json()

    async def fetch_financial_series(self, ticker: str) -> FinancialSeries:
        return await self._cache.get_or_fetch(
            (ticker, "financials"),
            lambda: self._fetch_financials(ticker),
        )

    async def _fetch_financials(self, ticker: str) -> FinancialSeries:
        cik = await self._ticker_to_cik(ticker)
        facts = await self.fetch_company_facts(cik)
        rows = _normalize_xbrl_to_rows(facts)
        if not rows:
            logger.warning(
                "sec_edgar empty XBRL units for %s (CIK %s)", ticker, cik
            )
        return FinancialSeries(
            ticker=ticker.upper(),
            period_type="annual",
            rows=rows,
            source="sec_edgar",
            fetched_at=datetime.now(timezone.utc),
        )

    async def fetch_sector(self, ticker: str) -> SectorInfo:
        cik = await self._ticker_to_cik(ticker)
        sub = await self._fetch_submissions(cik)
        sic = str(sub.get("sic", "")).zfill(4) if sub.get("sic") else ""
        gics = self._gics_for_sic(sic)
        if gics is None:
            logger.warning(
                "sec_edgar SIC %s for %s unmapped — sector=Unknown", sic, ticker
            )
            return SectorInfo(
                sector="Unknown",
                industry_group=None,
                confidence=SIC_MAPPING_MISS_CONFIDENCE,
                source="sec_edgar_sic",
            )
        return SectorInfo(
            sector=gics["sector"],
            industry_group=gics.get("industry_group"),
            confidence=SIC_MAPPING_HIT_CONFIDENCE,
            source="sec_edgar_sic",
        )

    async def fetch_fiscal_year_end(self, ticker: str) -> str | None:
        cik = await self._ticker_to_cik(ticker)
        sub = await self._fetch_submissions(cik)
        raw = sub.get("fiscalYearEnd")  # SEC returns "MMDD" or "0930"
        if not isinstance(raw, str) or len(raw) != 4 or not raw.isdigit():
            return None
        return f"{raw[:2]}-{raw[2:]}"

    async def _fetch_submissions(self, cik: str) -> dict:
        # Cache submissions by CIK — both fetch_sector and fetch_fiscal_year_end
        # hit it, but for the same ticker that's the same CIK.
        return await self._cache.get_or_fetch(
            (cik, "submissions"),
            lambda: self._do_fetch_submissions(cik),
        )

    async def _do_fetch_submissions(self, cik: str) -> dict:
        url = f"{SEC_DATA_BASE}/submissions/CIK{cik.zfill(10)}.json"
        client = await self._get_client()
        async with self._sem:
            r = await _retry_get(client, url)
        return r.json()

    async def fetch_8k_filings(
        self,
        ticker: str,
        *,
        since,
        item_code: str = "1.01",
    ) -> list[dict]:
        """List 8-K filings whose `items` include `item_code` and filed >= `since`.

        Returns dicts: {accession, filing_date, primary_document, items, cik}.
        Item 1.01 = "Entry into a Material Definitive Agreement" — the canonical
        contract source for P1.6 v2.

        Spec §6 / Plan P1.6 v2 §6.3.
        """
        cik = await self._ticker_to_cik(ticker)
        sub = await self._fetch_submissions(cik)
        recent = sub.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accs = recent.get("accessionNumber", [])
        items_arr = recent.get("items", [])
        docs = recent.get("primaryDocument", [])
        since_str = since.isoformat() if hasattr(since, "isoformat") else str(since)

        out: list[dict] = []
        for i, f in enumerate(forms):
            if f != "8-K":
                continue
            if dates[i] < since_str:
                continue
            row_items = items_arr[i] if i < len(items_arr) else ""
            if item_code and item_code not in str(row_items):
                continue
            out.append(
                {
                    "cik": cik,
                    "accession": accs[i],
                    "filing_date": dates[i],
                    "primary_document": docs[i] if i < len(docs) else None,
                    "items": str(row_items),
                }
            )
        return out

    async def fetch_10k_filings(
        self,
        ticker: str,
        *,
        since,
    ) -> list[dict]:
        """List 10-K (annual report) filings filed >= `since`.

        2026-05-14 Codex 권고 G — Item 1A. Risk Factors 가 명시한 customer/
        supplier/competitor가 매매 결정 baseline. 8-K 14일 윈도우 / news 14일
        윈도우 가 못 잡는 안정적 source.

        Returns: [{accession, filing_date, primary_document, cik}].
        보통 ticker 당 1년 1건. 최근 2년 윈도우로 1-2건 수렴.
        """
        cik = await self._ticker_to_cik(ticker)
        sub = await self._fetch_submissions(cik)
        recent = sub.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        since_str = since.isoformat() if hasattr(since, "isoformat") else str(since)

        out: list[dict] = []
        for i, f in enumerate(forms):
            if f != "10-K":
                continue
            if dates[i] < since_str:
                continue
            out.append(
                {
                    "cik": cik,
                    "accession": accs[i],
                    "filing_date": dates[i],
                    "primary_document": docs[i] if i < len(docs) else None,
                }
            )
        return out

    async def fetch_form4_filings(
        self,
        ticker: str,
        *,
        since,
    ) -> list[dict]:
        """List Form 4 (insider transactions) filings filed >= `since`.

        2026-05-14 Codex 시니어 트레이더 리뷰 권고 priority 3 — US 소/중형주
        insider 매수/매도가 매매 결정 context 의 절반. 8-K 패턴 그대로,
        form=='4' 필터.

        Returns: [{accession, filing_date, primary_document, cik}]. transaction
        code (P/S/A 등) 분류는 primary_document XML 파싱이 추가로 필요해 별도
        follow-up. 본 메서드는 filing 메타만.
        """
        cik = await self._ticker_to_cik(ticker)
        sub = await self._fetch_submissions(cik)
        recent = sub.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        since_str = since.isoformat() if hasattr(since, "isoformat") else str(since)

        out: list[dict] = []
        for i, f in enumerate(forms):
            if f != "4":
                continue
            if dates[i] < since_str:
                continue
            out.append(
                {
                    "cik": cik,
                    "accession": accs[i],
                    "filing_date": dates[i],
                    "primary_document": docs[i] if i < len(docs) else None,
                }
            )
        return out

    async def fetch_filing_body(
        self, *, cik: str, accession: str, primary_document: str
    ) -> str:
        """Fetch a filing's primary document HTML/text from SEC Archives.

        URL pattern: `Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary_doc}`.
        Returns plain text (HTML stripped) — caller passes to LLM.
        """
        if not primary_document:
            return ""
        cik_int = str(int(cik))
        acc_no_dashes = accession.replace("-", "")
        url = f"{SEC_ARCHIVES_BASE}/{cik_int}/{acc_no_dashes}/{primary_document}"

        client = await self._get_client()
        async with self._sem:
            r = await _retry_get(client, url)
        return _strip_html(r.text)

    async def _ticker_to_cik(self, ticker: str) -> str:
        if self._ticker_cik_map is None:
            self._ticker_cik_map = await self._load_ticker_cik_map()
        cik = self._ticker_cik_map.get(ticker.upper())
        if cik is None:
            raise ValueError(
                f"SEC EDGAR has no CIK for ticker {ticker!r}"
            )
        return cik

    async def _load_ticker_cik_map(self) -> dict[str, str]:
        if _TICKER_CACHE_PATH.exists():
            try:
                payload = json.loads(_TICKER_CACHE_PATH.read_text(encoding="utf-8"))
                return _parse_ticker_payload(payload)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("ticker→CIK cache read failed: %s", e)
        client = await self._get_client()
        async with self._sem:
            r = await _retry_get(client, SEC_TICKERS_URL)
        payload = r.json()
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            _TICKER_CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as e:
            logger.warning("ticker→CIK cache write failed: %s", e)
        return _parse_ticker_payload(payload)

    def _gics_for_sic(self, sic: str) -> dict | None:
        if self._gics_map is None:
            self._gics_map = _load_gics_map()
        return self._gics_map.get(sic)


# ---------------------------------------------------------------------------
# Module-level helpers (pure; trivially testable in isolation)
# ---------------------------------------------------------------------------


def _parse_ticker_payload(payload: Any) -> dict[str, str]:
    """SEC `company_tickers.json` → {ticker: cik_str}.

    Payload format (numeric keys → entry dicts):
        {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    """
    out: dict[str, str] = {}
    if not isinstance(payload, dict):
        return out
    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        ticker = entry.get("ticker")
        cik_int = entry.get("cik_str")
        if isinstance(ticker, str) and isinstance(cik_int, int):
            out[ticker.upper()] = str(cik_int)
    return out


async def _retry_get(
    client: httpx.AsyncClient, url: str, max_attempts: int = 3
) -> httpx.Response:
    """httpx GET with exponential backoff on 429/5xx; 4xx raises immediately."""
    delay = 0.5
    last: httpx.Response | None = None
    for attempt in range(1, max_attempts + 1):
        r = await client.get(url)
        last = r
        if r.status_code < 400:
            return r
        if r.status_code == 429 or 500 <= r.status_code < 600:
            if attempt < max_attempts:
                await asyncio.sleep(delay)
                delay *= 2
                continue
        # 4xx (non-429) or final retry exhaustion
        r.raise_for_status()
    assert last is not None
    last.raise_for_status()
    return last  # pragma: no cover (raise_for_status above always raises)


def _load_gics_map() -> dict[str, dict]:
    if not _GICS_PATH.exists():
        logger.warning(
            "sic_to_gics.json missing at %s — all SIC fall to Unknown",
            _GICS_PATH,
        )
        return {}
    try:
        payload = json.loads(_GICS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("sic_to_gics.json load failed: %s", e)
        return {}
    # Strip metadata keys (e.g., "_comment").
    return {k: v for k, v in payload.items() if not k.startswith("_") and isinstance(v, dict)}


def _normalize_xbrl_to_rows(facts: dict) -> list[dict]:
    """XBRL company facts → annual FY rows. Phase A: minimal taxonomy."""
    if not isinstance(facts, dict):
        return []
    facts_inner = facts.get("facts", {})
    if not isinstance(facts_inner, dict):
        return []
    us_gaap = facts_inner.get("us-gaap", {})
    if not isinstance(us_gaap, dict):
        return []

    by_period: dict[str, dict] = {}
    _collect_fy(us_gaap.get("Revenues"), by_period, "revenue")
    # Newer GAAP synonym used by Apple, Tesla, etc.
    _collect_fy(
        us_gaap.get("RevenueFromContractWithCustomerExcludingAssessedTax"),
        by_period, "revenue",
    )
    _collect_fy(us_gaap.get("NetIncomeLoss"), by_period, "net_income")
    _collect_fy(us_gaap.get("Assets"), by_period, "assets")

    return sorted(by_period.values(), key=lambda r: r.get("period", ""))


def _collect_fy(fact: Any, accumulator: dict[str, dict], key: str) -> None:
    if not isinstance(fact, dict):
        return
    units = fact.get("units")
    if not isinstance(units, dict):
        return
    for entries in units.values():
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict) or e.get("fp") != "FY":
                continue
            fy = e.get("fy")
            if not isinstance(fy, int):
                continue
            period = str(fy)
            row = accumulator.setdefault(period, {"period": period})
            row.setdefault(key, e.get("val"))  # first match per FY wins
        break  # one unit (USD) per fact is enough; ignore USD-per-share variants


def _strip_html(html: str) -> str:
    """HTML/XBRL → plain text. Used for 8-K filing bodies before LLM extraction.

    SEC 8-K HTML는 inline XBRL 태그가 많고, header/footer가 본문보다 길 때도
    있다. BeautifulSoup으로 script/style 제거 후 text 뽑고 whitespace 정리.
    """
    if not html:
        return ""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(("script", "style", "head", "meta", "link")):
        tag.decompose()
    text = soup.get_text(separator=" ")
    # Collapse runs of whitespace; preserve paragraph breaks via double newline.
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned
