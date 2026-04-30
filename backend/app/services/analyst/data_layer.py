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
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.database import async_session
from app.models import Financial, News, Stock
from app.models.relation import StockRelation
from app.schemas.card import (
    Citation,
    DataLayer,
    Fundamentals,
    MacroContext,
    NewsItem,
    Relation,
    TechMomentum,
)
from app.services.analyst.tools import (
    get_indicators,
    get_macro_context,
    llm_classify_news,
    llm_discover_relations,
)

logger = logging.getLogger(__name__)

NEWS_WINDOW_DAYS = 14
NEWS_SUMMARY_MAX = 300
RELATIONS_STALE_DAYS = 7
_VALID_RELATION_TYPES = {
    "peer", "supply_upstream", "supply_downstream", "group", "theme", "macro",
    # P1.6 v0+ — extracted via sector_match / sec_8k / news / dart_contract.
    "competitor", "contract_supplier", "contract_customer",
    "complementary", "regulatory_link",
}
_VALID_NEWS_IMPACTS = {"positive", "negative", "mixed", "neutral"}


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

    indicators_co, macro_co, fund_co, news_co, rel_co = await asyncio.gather(
        get_indicators(ticker),
        get_macro_context(),
        _fetch_fundamentals(ticker),
        _fetch_recent_news(ticker),
        _fetch_relations_data(ticker),
        return_exceptions=True,
    )

    pool = _CitationPool()

    technical = _build_technical(indicators_co, pool)
    macro = _build_macro(macro_co, pool)
    fundamentals = _build_fundamentals(fund_co, pool)
    news = await _build_news(news_co, pool)
    relations_data = _build_relations(rel_co, ticker, pool)

    if isinstance(rel_co, dict) and rel_co.get("is_stale"):
        # Fire-and-forget background refresh — do NOT await
        asyncio.create_task(_bg_refresh_relations(ticker))

    return DataLayer(
        technical=technical,
        macro=macro,
        fundamentals=fundamentals,
        news=news,
        relations_data=relations_data,
        data_citations=pool.items,
    )


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
        summary = (it.get("summary") or it.get("content") or "")[:NEWS_SUMMARY_MAX]
        items.append(
            NewsItem(
                title=title,
                source=source or "unknown",
                url=url,
                published_at=published_at,
                impact=impact,
                summary=summary,
                citation_id=cid,
            )
        )
    return items


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
                valid_from=r.get("valid_from"),
                valid_until=r.get("valid_until"),
            )
        )
    return out


# ---------------------------------------------------------------------------
# DB-backed fetchers (own session)
# ---------------------------------------------------------------------------


async def _fetch_fundamentals(ticker: str) -> dict:
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
        if not fin:
            return {"error": "재무 데이터 없음"}
        return {
            "per": fin.per,
            "pbr": fin.pbr,
            "market_cap_krw": float(fin.market_cap) if fin.market_cap else None,
            "dividend_yield": fin.dividend_yield,
            "per_5y_z": None,  # placeholder — needs 5y series; out of scope here
            "period": fin.period,
            "label": f"DB · financials ({fin.period})",
        }


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
                .limit(15)
            )
        ).scalars().all()
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
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"relations": [], "is_stale": False}
        rows = (
            await db.execute(
                select(StockRelation).where(StockRelation.from_stock_id == stock.id)
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
        for r in rows:
            tgt = targets.get(r.to_target)
            metadata = r.extra_metadata or {}
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
                    "valid_from": r.valid_from.isoformat() if r.valid_from else None,
                    "valid_until": r.valid_until.isoformat() if r.valid_until else None,
                }
            )
            if r.refreshed_at and (
                latest_refresh is None or r.refreshed_at > latest_refresh
            ):
                latest_refresh = r.refreshed_at

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


async def _bg_refresh_relations(ticker: str) -> None:
    """Fire-and-forget cache refresh. Errors are swallowed."""
    try:
        await llm_discover_relations(ticker)
    except Exception as e:  # noqa: BLE001
        logger.warning("bg relations refresh for %s failed: %s", ticker, e)


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
