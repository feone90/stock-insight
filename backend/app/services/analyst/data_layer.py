"""Data layer — server-produced sections for the v2 analyst card.

Runs 5 fetches in parallel via `asyncio.gather` and assembles a `DataLayer`.
Per-section graceful degrade: a sub-fetch failure leaves that section as
`None` / `[]` and is patched up by `engine.compose` (with a stub model so
the final `StockCard` contract still holds).

The analyst LLM (Stage 2) does NOT consume `DataLayer` directly — it reads
research notes from Stage 1. `DataLayer` is the canonical numbers that
land in the final card; `engine.compose` reconciles the two layers.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func as _f
from sqlalchemy import select

from app.database import async_session
from app.models import Financial, News, PriceHistory, Stock
from app.models.political_signal import PoliticalSignal, PoliticalSignalTicker
from app.models.relation import StockRelation
from app.models.relation_candidate import RelationCandidate
from app.collectors.krx_flow import fetch_kr_flow
from app.schemas.card import (
    AnalystRating,
    Citation,
    DataLayer,
    Earnings,
    Flow,
    Fundamentals,
    Insider,
    InsiderFiling,
    MacroContext,
    NewsItem,
    PoliticalSignalCard,
    PriceTarget,
    Relation,
    TechMomentum,
)
from app.services.analyst.tools import (
    get_indicators,
    get_macro_context,
    llm_classify_news,
    llm_discover_relations,
)
from app.services.ontology.evidence import (
    has_target_evidence,
    is_llm_source,
    rationale_admits_no_relationship,
)

logger = logging.getLogger(__name__)

NEWS_WINDOW_DAYS = 14
NEWS_SUMMARY_MAX = 300
RELATIONS_STALE_DAYS = 7
# 2026-05-15 — sector_match (confidence=0.4) 가 카드에 노이즈 도배되는 문제.
# read 시점 floor — 0.5 미만은 카드에 X. sector_match 자동 제외. LLM 추출
# (≥0.7) 와 dart_contract (≥0.6) 는 통과.
RELATIONS_MIN_CONFIDENCE = 0.5
_VALID_RELATION_TYPES = {
    "peer", "supply_upstream", "supply_downstream", "group", "theme", "macro",
    # P1.6 v0+ — extracted via sector_match / sec_8k / news / dart_contract.
    "competitor", "contract_supplier", "contract_customer",
    "complementary", "regulatory_link",
}
_VALID_NEWS_IMPACTS = {"positive", "negative", "mixed", "neutral"}
_BROAD_MARKET_TERMS = (
    "코스피", "코스닥", "증시", "시황", "장 초반", "장중", "외국인",
    "기관", "금리", "환율", "뉴욕증시", "나스닥", "시장",
)


class _CitationPool:
    """Sequential citation ID allocator for DataLayer's own pool (1..K)."""

    def __init__(self) -> None:
        self._items: list[Citation] = []
        self._next_id = 1

    def add(
        self,
        source_type: str,
        label: str,
        url: str | None = None,
        timestamp: datetime | None = None,
    ) -> int:
        cid = self._next_id
        self._items.append(
            Citation(id=cid, source_type=source_type, label=label, url=url, timestamp=timestamp)
        )
        self._next_id += 1
        return cid

    @property
    def items(self) -> list[Citation]:
        return list(self._items)


async def assemble_data_layer(ticker: str) -> DataLayer:
    """Fetch all deterministic sections in parallel; assemble into DataLayer.

    Each sub-fetch is wrapped so a single failure becomes a `None`/`[]`
    section + warning log, never an exception out of this function.
    """
    ticker = ticker.strip().upper()

    (
        indicators_co, macro_co, fund_co, news_co, rel_co, pol_co,
        flow_co, ins_co, earn_co, anal_co, pt_co, ts_co, move_co,
    ) = await asyncio.gather(
        get_indicators(ticker),
        get_macro_context(),
        _fetch_fundamentals(ticker),
        _fetch_recent_news(ticker),
        _fetch_relations_data(ticker),
        _fetch_political_signals(ticker),
        _fetch_flow(ticker),
        _fetch_insider(ticker),
        _fetch_earnings(ticker),
        _fetch_analyst_rating(ticker),
        _fetch_price_target(ticker),
        _fetch_data_timestamps(ticker),
        _fetch_recent_price_move_safe(ticker),
        return_exceptions=True,
    )

    pool = _CitationPool()

    technical = _build_technical(indicators_co, pool)
    macro = _build_macro(macro_co, pool)
    fundamentals = _build_fundamentals(fund_co, pool)
    news = await _build_news(news_co, pool)
    relations_data = _build_relations(rel_co, ticker, pool)
    political_signals = _build_political_signals(pol_co)
    flow = _build_flow(flow_co, pool)
    insider = _build_insider(ins_co, pool)
    earnings = _build_earnings(earn_co, pool)
    analyst_rating = _build_analyst_rating(anal_co, pool)
    price_target = _build_price_target(pt_co, pool)

    if isinstance(rel_co, dict) and rel_co.get("is_stale"):
        # Fire-and-forget background refresh — do NOT await
        asyncio.create_task(_bg_refresh_relations(ticker))

    price_asof, news_latest_at = _unpack_timestamps(ts_co)

    # RecentPriceMove instance 만 허용 — dict/None/Exception 모두 drop.
    from app.schemas.card import RecentPriceMove as _RecentPriceMove
    recent_move = move_co if isinstance(move_co, _RecentPriceMove) else None

    return DataLayer(
        technical=technical,
        macro=macro,
        fundamentals=fundamentals,
        flow=flow,
        insider=insider,
        earnings=earnings,
        analyst_rating=analyst_rating,
        price_target=price_target,
        news=news,
        political_signals=political_signals,
        relations_data=relations_data,
        recent_price_move=recent_move,
        data_citations=pool.items,
        price_asof=price_asof,
        news_latest_at=news_latest_at,
    )


async def _fetch_recent_price_move_safe(ticker: str):
    """fire-and-forget safe — assemble 흐름 안 깨지게 예외 swallow."""
    try:
        from app.services.analyst.price_move import fetch_recent_price_move

        return await fetch_recent_price_move(ticker)
    except Exception as e:  # noqa: BLE001
        logger.warning("recent_price_move failed for %s: %s", ticker, e)
        return None


# ---------------------------------------------------------------------------
# Section builders — each tolerates a None/Exception input
# ---------------------------------------------------------------------------


def _build_technical(res: Any, pool: _CitationPool) -> TechMomentum | None:
    if isinstance(res, Exception) or not isinstance(res, dict) or res.get("error"):
        if isinstance(res, Exception):
            logger.warning("data_layer indicators failed: %s", res)
        return None
    cite_label = "DB · price_history"
    if res.get("citations"):
        cite_label = res["citations"][0].get("label", cite_label)
    cid = pool.add("db", cite_label)
    return TechMomentum(
        rsi_14=res.get("rsi_14"),
        mfi_14=res.get("mfi_14"),
        atr_pct=res.get("atr_pct"),
        cmf_20=res.get("cmf_20"),
        obv_ratio=res.get("obv_ratio"),
        ma_stack=res.get("ma_stack"),
        rvol_20=res.get("rvol_20"),
        box_position=res.get("box_position"),
        summary_line=_format_tech_summary(res),
        citations=[cid],
    )


def _build_macro(res: Any, pool: _CitationPool) -> MacroContext | None:
    if isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer macro failed: %s", res)
        return None
    if not res.get("citations"):
        # Empty macro_factors table — skip rather than fabricate
        return None
    cite_label = res["citations"][0].get("label", "DB · macro_factors")
    cid = pool.add("market_data", cite_label)
    return MacroContext(
        one_line=_format_macro_one_line(res),
        vix=res.get("vix"),
        fx_pairs=res.get("fx_pairs", {}),
        us_10y=res.get("us_10y"),
        sensitivities=[],
        upcoming_events=res.get("upcoming_events", []),
        citations=[cid],
    )


def _build_earnings(res: Any, pool: _CitationPool) -> Earnings | None:
    if res is None or isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer earnings failed: %s", res)
        return None
    iso = res.get("date")
    if not iso:
        return None
    try:
        target = datetime.fromisoformat(iso).date()
        days_until = (target - datetime.utcnow().date()).days
    except Exception:  # noqa: BLE001
        days_until = 0
    pool.add("market_data", f"Finnhub · Earnings ({iso})")
    return Earnings(
        date=iso,
        days_until=days_until,
        eps_estimate=res.get("eps_estimate"),
        revenue_estimate=res.get("revenue_estimate"),
        hour=res.get("hour"),
    )


def _build_price_target(res: Any, pool: _CitationPool) -> PriceTarget | None:
    if res is None or isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer price target failed: %s", res)
        return None
    if not res.get("target_mean"):
        return None
    pool.add(
        "market_data",
        f"Finnhub · 분석가 목표주가 ({res.get('last_updated') or 'latest'})",
    )
    return PriceTarget(
        target_high=res.get("target_high"),
        target_low=res.get("target_low"),
        target_mean=res.get("target_mean"),
        target_median=res.get("target_median"),
        n_analysts=res.get("n_analysts"),
        last_updated=res.get("last_updated"),
    )


def _build_analyst_rating(res: Any, pool: _CitationPool) -> AnalystRating | None:
    if res is None or isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer analyst rating failed: %s", res)
        return None
    if not res.get("month"):
        return None
    rating = AnalystRating(
        month=res["month"],
        buy=res.get("buy", 0),
        hold=res.get("hold", 0),
        sell=res.get("sell", 0),
        strong_buy=res.get("strong_buy", 0),
        strong_sell=res.get("strong_sell", 0),
    )
    if rating.total == 0:
        return None
    pool.add("market_data", f"Finnhub · 분석가 의견 ({res['month']})")
    return rating


_SEC_ARCHIVE_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4"
)


def _build_insider(res: Any, pool: _CitationPool) -> Insider | None:
    """SEC Form 4 fetch 결과 → Insider. filing 0건 또는 fail 이면 None."""
    if res is None or isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer insider failed: %s", res)
        return None
    filings = res.get("filings") or []
    if not filings:
        return None
    cik = res.get("cik")
    pool.add(
        "disclosure",
        f"SEC EDGAR · Form 4 (최근 {res.get('window_days', 30)}일)",
        url=_SEC_ARCHIVE_URL.format(cik=cik) if cik else None,
    )
    recent = [
        InsiderFiling(
            filing_date=f.get("filing_date"),
            accession=f.get("accession"),
            url=f.get("url"),
        )
        for f in filings[:10]  # cap UI 노출
        if f.get("filing_date") and f.get("accession")
    ]
    return Insider(
        window_days=res.get("window_days", 30),
        filing_count=len(filings),
        recent=recent,
        as_of=res.get("as_of"),
    )


def _build_flow(res: Any, pool: _CitationPool) -> Flow | None:
    """pykrx 결과 → Flow. 모든 필드가 비어있으면 None (섹션 숨김).

    카드 노출 시 가족 친화 카피로 변환은 frontend 책임 — 여기선 raw 정량값만.
    """
    if res is None or isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer flow failed: %s", res)
        return None
    if res.get("error"):
        return None
    has_flow = (
        res.get("foreign_net_5d_krw") is not None
        or res.get("inst_net_5d_krw") is not None
    )
    if not has_flow:
        return None  # 수급 데이터 비면 섹션 자체를 숨긴다
    pool.add(
        "market_data",
        f"KRX 수급 ({res.get('as_of') or '최근'})",
    )
    return Flow(
        foreign_net_5d_krw=res.get("foreign_net_5d_krw"),
        inst_net_5d_krw=res.get("inst_net_5d_krw"),
        foreign_streak_days=res.get("foreign_streak_days") or 0,
        inst_streak_days=res.get("inst_streak_days") or 0,
        as_of=res.get("as_of"),
    )


def _build_fundamentals(res: Any, pool: _CitationPool) -> Fundamentals | None:
    if isinstance(res, Exception) or not isinstance(res, dict) or res.get("error"):
        if isinstance(res, Exception):
            logger.warning("data_layer fundamentals failed: %s", res)
        return None
    label = res.get("label") or f"DB · financials ({res.get('period', 'latest')})"
    cid = pool.add("db", label)
    return Fundamentals(
        per=res.get("per"),
        pbr=res.get("pbr"),
        market_cap_krw=res.get("market_cap_krw"),
        dividend_yield=res.get("dividend_yield"),
        per_5y_z=res.get("per_5y_z"),
        source_label=label,
        citations=[cid],
    )


async def _build_news(res: Any, pool: _CitationPool) -> list[NewsItem]:
    if isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer news failed: %s", res)
        return []
    raw_items: list[dict] = res.get("items", [])
    if not raw_items:
        return []

    impacts = await _classify_impacts(raw_items)
    analyses = await _analyze_news_items(raw_items)

    items: list[NewsItem] = []
    for idx, it in enumerate(raw_items):
        title = it.get("title", "")
        source = it.get("source", "") or ""
        url = it.get("url", "") or ""
        published_at = it.get("published_at")
        if not isinstance(published_at, datetime) or not title or not url:
            continue
        impact = impacts.get(idx, "neutral")
        if impact not in _VALID_NEWS_IMPACTS:
            impact = "neutral"
        cid = pool.add(
            "news",
            label=f"{source} · {title}"[:200],
            url=url,
            timestamp=published_at,
        )
        raw_summary = (it.get("summary") or it.get("content") or "")
        fallback = _fallback_news_analysis(raw_summary, title)
        analysis = analyses.get(idx, {})
        summary = analysis.get("summary") or fallback["summary"]
        key_quote = _validated_quote(
            analysis.get("key_quote"),
            raw_summary,
        ) or fallback.get("key_quote")
        why_it_matters = analysis.get("why_it_matters") or fallback.get("why_it_matters")
        items.append(
            NewsItem(
                title=title,
                source=source or "unknown",
                url=url,
                published_at=published_at,
                impact=impact,
                summary=summary,
                key_quote=key_quote,
                why_it_matters=why_it_matters,
                citation_id=cid,
            )
        )
    return items


def _compact_text(value: str | None) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", value or "").lower()


def _stock_news_aliases(stock: Stock) -> set[str]:
    aliases = {stock.ticker, stock.name}
    if stock.name.endswith("보통주"):
        aliases.add(stock.name.removesuffix("보통주"))
    simplified = _simplify_company_name(stock.name)
    if simplified:
        aliases.add(simplified)
    return {a for a in aliases if a}


def _simplify_company_name(name: str | None) -> str:
    if not name:
        return ""
    cleaned = re.sub(
        r"\b(incorporated|inc|corp|corporation|company|co|ltd|limited|plc|holdings|holding|class\s+[a-z])\b\.?",
        "",
        name,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned.replace(",", " ")).strip()
    return cleaned


def _news_relevance_score(stock: Stock, row: News) -> int:
    title = row.title or ""
    content = row.content or ""
    title_norm = _compact_text(title)
    body_norm = _compact_text(content)
    aliases = [_compact_text(a) for a in _stock_news_aliases(stock)]

    score = 0
    for alias in aliases:
        if not alias or len(alias) < 2:
            continue
        if alias in title_norm:
            score += 8
        elif alias in body_norm:
            score += 3

    if any(term in title for term in _BROAD_MARKET_TERMS):
        score -= 2
    # If the article never names the stock, it is not a stock-specific card item.
    return score


def _news_summary(raw_summary: str, title: str) -> str:
    return _fallback_news_analysis(raw_summary, title)["summary"]


def _fallback_news_analysis(raw_summary: str, title: str) -> dict[str, str | None]:
    body = (raw_summary or "").strip()
    key_quote = _select_key_quote(body)
    if body:
        sentence = _first_sentences(body, max_chars=NEWS_SUMMARY_MAX)
        return {
            "summary": sentence or body[:NEWS_SUMMARY_MAX],
            "key_quote": key_quote,
            "why_it_matters": None,
        }
    clean_title = re.sub(r"\s+", " ", (title or "").strip())
    if not clean_title:
        return {"summary": "", "key_quote": None, "why_it_matters": None}
    return {
        "summary": f"핵심: {clean_title}"[:NEWS_SUMMARY_MAX],
        "key_quote": None,
        "why_it_matters": None,
    }


def _first_sentences(text: str, max_chars: int = NEWS_SUMMARY_MAX) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    out = ""
    for sentence in sentences[:2]:
        candidate = f"{out} {sentence}".strip()
        if len(candidate) > max_chars:
            break
        out = candidate
    return out or sentences[0][:max_chars]


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?。！？다요죠음임함됨함다])\s+", cleaned)
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def _select_key_quote(text: str) -> str | None:
    for sentence in _split_sentences(text):
        if len(sentence) > 140:
            sentence = sentence[:137].rstrip() + "..."
        return sentence
    return None


def _validated_quote(candidate: str | None, body: str) -> str | None:
    quote = (candidate or "").strip().strip('"“”')
    if not quote:
        return None
    compact_body = re.sub(r"\s+", "", body or "")
    compact_quote = re.sub(r"\s+", "", quote)
    if compact_quote and compact_quote in compact_body:
        return quote[:140]
    return None


def _build_relations(
    res: Any, ticker: str, pool: _CitationPool
) -> list[Relation]:
    if isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer relations failed: %s", res)
        return []
    rels: list[dict] = res.get("relations", [])
    if not rels:
        return []
    out: list[Relation] = []
    for r in rels:
        rtype = r.get("relation_type")
        if rtype not in _VALID_RELATION_TYPES:
            continue
        target_ticker = r.get("target_ticker") or ""
        if not target_ticker:
            continue
        cid = pool.add(
            "curated_relation",
            label=f"AI 큐레이션 · {ticker} → {target_ticker} ({rtype})",
        )
        try:
            strength = float(r.get("strength", 0.5))
        except (TypeError, ValueError):
            strength = 0.5
        strength = max(0.0, min(1.0, strength))
        try:
            confidence = float(r.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        signal = r.get("signal_direction") or "positive"
        if signal not in {"positive", "negative", "inverse"}:
            signal = "positive"
        cc_raw = r.get("customer_concentration_pct")
        cc: float | None
        try:
            cc = float(cc_raw) if cc_raw is not None else None
            if cc is not None and not (0 <= cc <= 100):
                cc = None
        except (TypeError, ValueError):
            cc = None

        out.append(
            Relation(
                target_ticker=target_ticker,
                target_name=r.get("target_name") or target_ticker,
                relation_type=rtype,  # type: ignore[arg-type]
                strength=strength,
                today_change_pct=r.get("today_change_pct"),
                notes=None,  # filled by analyst's relations_narrative at compose
                citation_ids=[cid],
                signal_direction=signal,  # type: ignore[arg-type]
                confidence=confidence,
                source=r.get("source") or "curated_relation",
                source_url=r.get("source_url"),
                rationale=r.get("rationale"),
                valid_from=r.get("valid_from"),
                valid_until=r.get("valid_until"),
                customer_concentration_pct=cc,
                target_is_public=bool(r.get("target_is_public", True)),
                business_importance=r.get("business_importance"),
            )
        )
    return out


# ---------------------------------------------------------------------------
# DB-backed fetchers (own session)
# ---------------------------------------------------------------------------


async def _fetch_earnings(ticker: str) -> dict | None:
    from app.collectors.finnhub import fetch_earnings_calendar
    from app.markets import is_us

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock or not is_us(stock.market):
            return None
    return await fetch_earnings_calendar(ticker)


async def _fetch_analyst_rating(ticker: str) -> dict | None:
    from app.collectors.finnhub import fetch_analyst_recommendation
    from app.markets import is_us

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock or not is_us(stock.market):
            return None
    return await fetch_analyst_recommendation(ticker)


async def _fetch_price_target(ticker: str) -> dict | None:
    from app.collectors.finnhub import fetch_price_target
    from app.markets import is_us

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock or not is_us(stock.market):
            return None
    return await fetch_price_target(ticker)


_FORM4_WINDOW_DAYS = 30


async def _fetch_insider(ticker: str) -> dict | None:
    """US 종목 한정 — SEC Form 4 최근 30일 filings. KR 종목은 None."""
    from app.markets import is_us
    from app.services.external_data_adapters import get_adapter_for

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock or not is_us(stock.market):
            return None

    adapter = get_adapter_for(ticker)
    if adapter is None or not hasattr(adapter, "fetch_form4_filings"):
        return None

    since = (datetime.utcnow() - timedelta(days=_FORM4_WINDOW_DAYS)).date()
    try:
        filings = await adapter.fetch_form4_filings(ticker, since=since)
    except Exception as e:  # noqa: BLE001
        logger.warning("Form 4 fetch failed for %s: %s", ticker, e)
        return None

    if not filings:
        return None
    cik = filings[0].get("cik")
    cik_int = str(int(cik)) if cik else None
    out_filings: list[dict] = []
    for f in filings:
        acc = f.get("accession") or ""
        primary = f.get("primary_document")
        url = None
        if cik_int and acc and primary:
            acc_no_dashes = acc.replace("-", "")
            url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik_int}/{acc_no_dashes}/{primary}"
            )
        out_filings.append(
            {
                "filing_date": f.get("filing_date"),
                "accession": acc,
                "url": url,
            }
        )
    return {
        "cik": cik,
        "window_days": _FORM4_WINDOW_DAYS,
        "filings": out_filings,
        "as_of": (
            max((f.get("filing_date") or "" for f in out_filings), default=None)
            or None
        ),
    }


async def _fetch_flow(ticker: str) -> dict | None:
    """KR 종목 한정 — pykrx 수급/공매도 스냅샷. US/없는 종목은 None."""
    from app.markets import is_kr

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock or not is_kr(stock.market):
            return None
    return await asyncio.to_thread(fetch_kr_flow, ticker)


async def _fetch_fundamentals(ticker: str) -> dict:
    from app.markets import is_kr

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}' 없음"}
        fin = (
            await db.execute(
                select(Financial)
                .where(Financial.stock_id == stock.id)
                .order_by(Financial.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if fin:
            label = _label_for_financial(fin, is_kr(stock.market))
            return {
                "per": fin.per,
                "pbr": fin.pbr,
                "market_cap_krw": float(fin.market_cap) if fin.market_cap else None,
                "dividend_yield": fin.dividend_yield,
                "per_5y_z": None,  # needs 5y series
                "period": fin.period,
                "label": label,
            }
        # Fallback: Stock.market_cap only (universe seed 단계). Financial row
        # 자체가 없음 — 사용자에게 "데이터 미수집" 명시.
        if stock.market_cap is not None:
            return {
                "per": None,
                "pbr": None,
                "market_cap_krw": float(stock.market_cap),
                "dividend_yield": None,
                "per_5y_z": None,
                "period": None,
                "label": "시총만 — 재무 미수집 (분석 시작 전)",
            }
        return {"error": "재무 데이터 없음"}


def _label_for_financial(fin: "Financial", kr: bool) -> str:  # type: ignore[name-defined]
    """Financial row 의 채워진 필드 모양으로 출처 추정.

    - KR + revenue 있음             → "DART · 사업보고서 ({period})"
    - KR + revenue 없음 + KRX 비율  → "KRX 공식 시세 (PER/PBR 일별)" — pykrx 보강
    - KR + 시총만                    → "시총만 (DART 사업보고서 미공개)"
    - US                            → "yfinance · TTM ({period})"
    """
    if not kr:
        return f"yfinance · TTM ({fin.period})"
    if fin.revenue is not None:
        return f"DART · 사업보고서 ({fin.period})"
    if fin.per is not None or fin.pbr is not None:
        return "KRX 공식 시세 (PER/PBR 일별)"
    return "시총만 (DART 사업보고서 미공개)"


# 2026-05-19 — 정치 시그널 노출 정책 (Codex review 적용).
# 단순 14일 윈도우 → expected_window + strength + confidence 종합 score.
# DB 에 박혀있던 영향력 정보를 활용해 시니어 분석가 시각으로 *지금 의사결정에
# 의미 있는* 시그널만 노출.
_PS_EXPECTED_WINDOW_DAYS = {
    "minutes": 1,      # 0.04일이지만 최소 1일 (당일 보존)
    "hours": 2,        # 48시간
    "1-3days": 5,      # 5일
    "1-2weeks": 14,    # 14일
}
_PS_STRENGTH_MAX_DAYS = {
    "low": 7,
    "medium": 14,
    "high": 21,
}
_PS_MIN_CONFIDENCE = 0.5  # 그 이하는 자동 매매 제외 (model 주석에서)
_PS_MAX_FETCH_WINDOW_DAYS = 30  # DB 조회 상한 (status="expired" 도 일부 history 용)


async def _fetch_political_signals(ticker: str) -> dict:
    """이 ticker에 매핑된 political_signals + status 분류.

    필터 (Codex review 2026-05-19):
      1. confidence ≥ 0.5 (그 이하 자동 제외)
      2. expected_window 기반 만료 (예: hours=48h, 1-2weeks=14d)
      3. strength 기반 수명 상한 (low=7d, medium=14d, high=21d)
      4. 둘 중 더 짧은 만료 적용

    status 분류:
      - new      : 24시간 이내
      - active   : 만료 안 됨 + 24h+
      - fading   : 만료 임박 (남은 수명 < 30%)
      - expired  : 만료 — 기본 카드 비노출 (history view 용으로 fetch 만)

    Returns {"items": list[dict]} 단, expired 는 호출자가 별도 처리.
    """
    now = datetime.utcnow()
    fetch_cutoff = now - timedelta(days=_PS_MAX_FETCH_WINDOW_DAYS)
    async with async_session() as db:
        rows = (
            await db.execute(
                select(PoliticalSignal, PoliticalSignalTicker)
                .join(
                    PoliticalSignalTicker,
                    PoliticalSignalTicker.signal_id == PoliticalSignal.id,
                )
                .where(
                    PoliticalSignalTicker.ticker == ticker,
                    PoliticalSignal.analyzed_at.isnot(None),
                    PoliticalSignal.is_market_relevant.is_(True),
                    PoliticalSignal.posted_at >= fetch_cutoff,
                    PoliticalSignal.source != "sample_macro",
                )
                .order_by(PoliticalSignal.posted_at.desc())
                .limit(20)
            )
        ).all()

    items: list[dict] = []
    for signal, impact in rows:
        # 가드 1: confidence floor
        if (impact.confidence or 0) < _PS_MIN_CONFIDENCE:
            continue

        if signal.posted_at is None:
            continue
        age_days = (now - signal.posted_at).total_seconds() / 86400.0
        days_old = int(age_days)

        # 가드 2+3: expected_window + strength 중 *더 짧은* 만료.
        window_days = _PS_EXPECTED_WINDOW_DAYS.get(impact.expected_window, 14)
        strength_days = _PS_STRENGTH_MAX_DAYS.get(impact.strength, 14)
        max_days = min(window_days, strength_days)

        # status 분류
        if age_days > max_days:
            status = "expired"
        elif age_days < 1:
            status = "new"
        elif age_days > max_days * 0.7:
            status = "fading"
        else:
            status = "active"

        # 기본 fetch 결과는 expired 제외. history view (admin) 가 별도로 필요시.
        if status == "expired":
            continue

        items.append(
            {
                "posted_at": signal.posted_at,
                "author": signal.author,
                "source": signal.source,
                "url": signal.url,
                "summary_ko": signal.summary_ko or "",
                "overall_sentiment": signal.overall_sentiment or "neutral",
                "macro_themes": signal.macro_themes or [],
                "sentiment": impact.sentiment,
                "direction": impact.direction,
                "strength": impact.strength,
                "confidence": impact.confidence,
                "expected_window": impact.expected_window,
                "reasoning": impact.reasoning,
                "sector_impact": impact.sector_impact,
                "status": status,
                "days_old": days_old,
            }
        )
    return {"items": items[:10]}  # 최대 10개


def _build_political_signals(res: Any) -> list[PoliticalSignalCard]:
    """political_signals raw → PoliticalSignalCard list. fail 시 빈 list."""
    if isinstance(res, Exception) or not isinstance(res, dict) or res.get("error"):
        if isinstance(res, Exception):
            logger.warning("data_layer political signals failed: %s", res)
        return []
    items = res.get("items") or []
    out: list[PoliticalSignalCard] = []
    for it in items:
        try:
            out.append(PoliticalSignalCard.model_validate(it))
        except Exception as e:  # noqa: BLE001
            logger.warning("political signal validation skip: %s", e)
    return out


async def _fetch_data_timestamps(ticker: str) -> dict:
    """Per-layer "마지막 갱신" 시각을 한 번에 계산해 카드에 넘긴다.

    - price_asof : Stock.last_price_sync_at (sync_prices 호출 시각) 우선,
      fallback MAX(PriceHistory.date). 2026-05-15 fix — 같은 날 sync 여러
      번 해도 시각이 advance 해야 frontend polling 이 감지.
    - news_latest_at : MAX(News.published_at).
    """
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"price_asof": None, "news_latest_at": None}
        price_sync_at = stock.last_price_sync_at
        price_row = None
        if price_sync_at is None:
            price_row = (
                await db.execute(
                    select(_f.max(PriceHistory.date)).where(
                        PriceHistory.stock_id == stock.id
                    )
                )
            ).scalar()
        news_row = (
            await db.execute(
                select(_f.max(News.published_at)).where(News.stock_id == stock.id)
            )
        ).scalar()

    # 2026-05-15 timezone bug fix — DB DateTime 컬럼이 naive (tzinfo=None) 라
    # serialize 시 KST 환경 frontend 가 9시간 어긋남. 모든 timestamp 에 UTC
    # 강제 부착 후 반환.
    def _ensure_utc(dt):
        if dt is None:
            return None
        if hasattr(dt, "tzinfo") and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    price_asof: datetime | None = None
    if price_sync_at is not None:
        price_asof = _ensure_utc(price_sync_at)
    elif price_row is not None:
        if isinstance(price_row, datetime):
            price_asof = _ensure_utc(price_row)
        else:
            price_asof = datetime.combine(price_row, datetime.min.time(), tzinfo=timezone.utc)

    news_latest_at: datetime | None = None
    if isinstance(news_row, datetime):
        news_latest_at = _ensure_utc(news_row)

    return {"price_asof": price_asof, "news_latest_at": news_latest_at}


def _unpack_timestamps(res: Any) -> tuple[datetime | None, datetime | None]:
    if isinstance(res, Exception) or not isinstance(res, dict):
        if isinstance(res, Exception):
            logger.warning("data_layer timestamps failed: %s", res)
        return None, None
    return res.get("price_asof"), res.get("news_latest_at")


async def _fetch_recent_news(ticker: str) -> dict:
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"items": []}
        cutoff = datetime.utcnow() - timedelta(days=NEWS_WINDOW_DAYS)
        rows = (
            await db.execute(
                select(News)
                .where(News.stock_id == stock.id, News.published_at >= cutoff)
                .order_by(News.published_at.desc())
                .limit(40)
            )
        ).scalars().all()
        ranked = sorted(
            (
                (_news_relevance_score(stock, n), n)
                for n in rows
            ),
            key=lambda item: (item[0], item[1].published_at or datetime.min),
            reverse=True,
        )
        rows = [n for score, n in ranked if score > 0][:15]
        items = [
            {
                "title": n.title,
                "source": n.source,
                "url": n.url,
                "published_at": n.published_at,
                "summary": (n.content or "")[:NEWS_SUMMARY_MAX],
            }
            for n in rows
        ]
        return {"items": items}


async def _fetch_relations_data(ticker: str) -> dict:
    """카드용 모든 관계 반환. frontend 에서 3-tier visual strata 로 표현.

    2026-05-14: 처음엔 sector_match 를 server-side 제외했지만 사용자 피드백
    ("관계 너무 안뽑혀도 문제 너무 뽑혀도 문제, 촘촘하게 엮여있는 관계도
    좋아, 그 가운데 어떤게 확실히 유의미한지 눈에 보기 좋게") 으로 정정.

    카드는 모든 관계를 받되 frontend 가 core / business / context 3층으로
    시각 차별. 정보 손실 0, 의미 가시성 ↑.

    project_ontology_codex_review_2026_05_14 메모 참조.
    """
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"relations": [], "is_stale": False}
        rows = (
            await db.execute(
                select(StockRelation).where(
                    StockRelation.from_stock_id == stock.id,
                    StockRelation.is_active.is_(True),
                    StockRelation.confidence >= RELATIONS_MIN_CONFIDENCE,
                )
            )
        ).scalars().all()

        target_tickers = [r.to_target for r in rows if r.to_kind == "stock"]
        targets: dict[str, Stock] = {}
        if target_tickers:
            ts = (
                await db.execute(
                    select(Stock).where(Stock.ticker.in_(target_tickers))
                )
            ).scalars().all()
            targets = {s.ticker: s for s in ts}

        relations: list[dict] = []
        latest_refresh: datetime | None = None
        hallucination_ids: list[int] = []
        for r in rows:
            tgt = targets.get(r.to_target)
            metadata = r.extra_metadata or {}
            rationale = (
                metadata.get("rationale") if isinstance(metadata, dict) else None
            )
            # Defense in depth at read path (2026-05-14 SK하이닉스→동화약품 사례).
            # validator 가드는 prevention 만 — 옛 row 가 DB 에 남아있어도 사용자
            # 화면에 절대 안 보이게 read 시점에서 다시 검사. + 검출되면 soft
            # delete (is_active=False) 로 DB 자기 청소 — 다음 fetch 부터 query
            # 자체에서 제외.
            if is_llm_source(r.source):
                target_name = tgt.name if tgt else None
                # (a) 자기 부정 rationale ("NVDA와의 직접 관계는 없음" 류).
                # (b) target name/ticker 본문 substring 부재.
                # 두 케이스 모두 hide + soft-delete.
                if rationale_admits_no_relationship(rationale):
                    hallucination_ids.append(r.id)
                    logger.warning(
                        "data_layer hide+soft-delete self-negating rationale: "
                        "%s→%s src=%s rationale=%r",
                        ticker, r.to_target, r.source,
                        (rationale or "")[:120],
                    )
                    continue
                if not has_target_evidence(rationale, target_name, r.to_target):
                    hallucination_ids.append(r.id)
                    logger.warning(
                        "data_layer hide+soft-delete hallucination: "
                        "%s→%s src=%s rationale=%r",
                        ticker, r.to_target, r.source,
                        (rationale or "")[:80],
                    )
                    continue
            relations.append(
                {
                    "target_ticker": r.to_target,
                    "target_name": tgt.name if tgt else r.to_target,
                    "relation_type": r.relation_type,
                    "strength": r.strength,
                    "today_change_pct": tgt.change_percent if tgt else None,
                    # P1.6 v0+ — surface discovery signals to the card.
                    "signal_direction": r.signal_direction or "positive",
                    "confidence": r.confidence if r.confidence is not None else 0.5,
                    "source": r.source,
                    "source_url": metadata.get("source_url") if isinstance(metadata, dict) else None,
                    "rationale": rationale,
                    "customer_concentration_pct": (
                        metadata.get("customer_concentration_pct") if isinstance(metadata, dict) else None
                    ),
                    # 2026-05-15 — llm_knowledge source 가 metadata 에 박는다.
                    "business_importance": (
                        metadata.get("business_importance") if isinstance(metadata, dict) else None
                    ),
                    "target_is_public": True,  # StockRelation 은 항상 상장 universe
                    "valid_from": r.valid_from.isoformat() if r.valid_from else None,
                    "valid_until": r.valid_until.isoformat() if r.valid_until else None,
                }
            )
            if r.refreshed_at and (
                latest_refresh is None or r.refreshed_at > latest_refresh
            ):
                latest_refresh = r.refreshed_at

        # Soft-delete detected hallucinations — fire-and-forget. is_active=False
        # 로 mark 하면 다음 fetch 부터 query (의 is_active=True 필터) 에서 제외.
        # 별도 background task — read 응답 지연 X.
        if hallucination_ids:
            asyncio.create_task(_soft_delete_relations(hallucination_ids))

        # 2026-05-15 — knowledge_relations 의 비상장 entity (OpenAI, SpaceX 등)
        # 는 RelationCandidate 에 source="llm_knowledge" 로 buffer. 카드에 별도
        # "전략 파트너 (비상장)" 으로 surface 해서 사용자가 진짜 중요한 관계 봄.
        # candidate 는 universe gap 으로 promote 안 됐을 뿐, 데이터 quality 동일.
        cand_rows = (
            await db.execute(
                select(RelationCandidate).where(
                    RelationCandidate.from_ticker == ticker,
                    RelationCandidate.source == "llm_knowledge",
                    RelationCandidate.promoted_at.is_(None),
                )
            )
        ).scalars().all()
        for c in cand_rows:
            c_meta = c.extra_metadata or {}
            target_name = (
                c_meta.get("target_name") if isinstance(c_meta, dict) else None
            ) or c.to_ticker
            relations.append({
                "target_ticker": c.to_ticker,
                "target_name": target_name,
                "relation_type": c.relation_type,
                "strength": c.strength if c.strength is not None else 0.6,
                "today_change_pct": None,  # 비상장 — 시세 없음
                "signal_direction": c.signal_direction or "positive",
                "confidence": c.confidence if c.confidence is not None else 0.7,
                "source": c.source,
                "source_url": None,
                "rationale": c_meta.get("rationale") if isinstance(c_meta, dict) else None,
                "customer_concentration_pct": None,
                "business_importance": (
                    c_meta.get("business_importance") if isinstance(c_meta, dict) else None
                ),
                "target_is_public": False,  # 비상장 — frontend 가 다르게 그림
                "valid_from": None,
                "valid_until": None,
            })

        is_stale = (
            latest_refresh is not None
            and (datetime.utcnow() - latest_refresh) > timedelta(days=RELATIONS_STALE_DAYS)
        )
        return {"relations": relations, "is_stale": is_stale}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _classify_impacts(items: list[dict]) -> dict[int, str]:
    """Best-effort news classification. On any failure, return empty map
    (callers default to 'neutral')."""
    try:
        result = await llm_classify_news(items)
        out: dict[int, str] = {}
        for entry in result.get("items", []):
            idx = entry.get("index")
            impact = entry.get("impact")
            if isinstance(idx, int) and impact in _VALID_NEWS_IMPACTS:
                out[idx] = impact
        return out
    except Exception as e:  # noqa: BLE001 - degrade quietly
        logger.warning("data_layer news classify failed: %s", e)
        return {}


def _is_mostly_english(text: str) -> bool:
    """ASCII-letter ratio ≥ 0.5 means the body is in English (or mostly so).
    Korean / Japanese / Chinese characters all fail this check, so they're
    served as-is."""
    if not text:
        return False
    sample = text[:600]
    letters = [c for c in sample if c.isalpha()]
    if len(letters) < 30:
        return False
    ascii_letters = sum(1 for c in letters if c.isascii())
    return ascii_letters / len(letters) >= 0.5


async def _analyze_news_items(items: list[dict]) -> dict[int, dict[str, str]]:
    """Produce card-ready Korean analysis for substantial news bodies.

    Returns {index: {summary, key_quote, why_it_matters}}. Failures degrade
    quietly to {} so the news section still renders with local fallbacks.
    """
    target_indices: list[int] = []
    for i, it in enumerate(items):
        body = (it.get("summary") or it.get("content") or "")
        if _is_mostly_english(body) or len(body.strip()) >= 80:
            target_indices.append(i)
    if not target_indices:
        return {}

    payload_lines: list[str] = []
    for i in target_indices:
        body = (items[i].get("summary") or items[i].get("content") or "")[:600]
        title = items[i].get("title", "")
        payload_lines.append(f"[{i}] TITLE: {title}\nBODY: {body}")
    payload = "\n\n".join(payload_lines)

    prompt = (
        "다음은 주식 카드에 표시할 최근 뉴스다. 각 항목마다 아래 3가지를 뽑아라.\n"
        "1) summary: 제목 반복 금지. 기사 본문이 실제로 말하는 내용을 한국어 한 문장으로 요약.\n"
        "2) key_quote: 투자 판단에 중요한 원문 문장 1개를 BODY에서 그대로 짧게 인용. 없으면 빈 문자열.\n"
        "3) why_it_matters: 해당 종목의 실적·주가·사업에 왜 중요한지 한국어 한 문장.\n"
        "확인되지 않은 전망은 단정하지 말고, BODY에 없는 내용은 만들지 마라.\n\n"
        f"{payload}\n\n"
        '응답은 JSON 객체 1개:\n'
        '{ "items": { "0": { "summary": "...", "key_quote": "...", "why_it_matters": "..." } } }\n'
        "자연어 설명 / 코드펜스 X. 빠진 인덱스는 빈 응답."
    )

    try:
        from app.services.llm.adapter import get_adapter
        raw = await get_adapter().generate_json(prompt)
        import json as _json
        parsed = _json.loads(raw) if isinstance(raw, str) else raw
        raw_items = parsed.get("items", {}) if isinstance(parsed, dict) else {}
        out: dict[int, dict[str, str]] = {}
        for k, v in raw_items.items():
            if not isinstance(v, dict):
                continue
            try:
                idx = int(k)
            except (TypeError, ValueError):
                continue
            summary = str(v.get("summary") or "").strip()[:NEWS_SUMMARY_MAX]
            key_quote = str(v.get("key_quote") or "").strip()[:140]
            why = str(v.get("why_it_matters") or "").strip()[:220]
            if summary or key_quote or why:
                out[idx] = {
                    "summary": summary,
                    "key_quote": key_quote,
                    "why_it_matters": why,
                }
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("news item analysis failed: %s", e)
        return {}


async def _bg_refresh_relations(ticker: str) -> None:
    """Fire-and-forget cache refresh. Errors are swallowed."""
    try:
        await llm_discover_relations(ticker)
    except Exception as e:  # noqa: BLE001
        logger.warning("bg relations refresh for %s failed: %s", ticker, e)


async def _soft_delete_relations(ids: list[int]) -> None:
    """Read-time hallucination 감지된 row id 를 is_active=False 로 mark.

    DELETE 대신 soft-delete — query 의 `is_active=True` 필터로 자연스럽게 제외
    되고, false positive 시 admin 이 복구 가능. 다음 fetch 부터 사용자 화면
    에 안 보이고, purge_noise 호출하면 영구 삭제.
    """
    from sqlalchemy import update

    from app.models.relation import StockRelation

    try:
        async with async_session() as db:
            await db.execute(
                update(StockRelation)
                .where(StockRelation.id.in_(ids))
                .values(is_active=False)
            )
            await db.commit()
        logger.info("soft-deleted %d hallucination relations: %s", len(ids), ids)
    except Exception as e:  # noqa: BLE001
        logger.warning("soft-delete relations failed for %s: %s", ids, e)


def _format_tech_summary(res: dict) -> str:
    parts: list[str] = []
    rsi = res.get("rsi_14")
    if rsi is not None:
        parts.append(f"RSI {rsi:.0f}")
    ma = res.get("ma_stack")
    if ma:
        parts.append(str(ma))
    rvol = res.get("rvol_20")
    if rvol is not None:
        parts.append(f"RVOL {rvol:.1f}x")
    return ", ".join(parts) if parts else "지표 데이터 부족"


def _format_macro_one_line(res: dict) -> str:
    parts: list[str] = []
    fx = res.get("fx_pairs") or {}
    if "USD/KRW" in fx and fx["USD/KRW"] is not None:
        parts.append(f"USD/KRW {fx['USD/KRW']:.0f}")
    if res.get("us_10y") is not None:
        parts.append(f"미 10Y {res['us_10y']:.2f}%")
    if res.get("vix") is not None:
        parts.append(f"VIX {res['vix']:.1f}")
    return ", ".join(parts) if parts else "매크로 스냅샷"


# Identity helper — extracted from the old synthesize._fetch_stock_metadata
# so engine.compose can server-inject without touching synthesize.
async def fetch_stock_identity(ticker: str) -> dict:
    """DB-sourced fields the server fills on the final card.
    LLM never produces these — compose injects them last so they win."""
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"ticker": ticker}
        return {
            "ticker": stock.ticker,
            "name_ko": stock.name or "",
            "name_en": stock.name or "",
            "market": stock.market or "",
            "sector": stock.sector or "",
            "tags": [],
            "price": stock.current_price or 0.0,
            "change": stock.change or 0.0,
            "change_pct": stock.change_percent or 0.0,
            "asof": datetime.now(timezone.utc),
        }
