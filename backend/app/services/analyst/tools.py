"""Tools exposed to the v2 research agent (Stage 1).

Each tool returns dict with `citations` populated. Citations have
source_type from {db, market_data, news, disclosure, web, curated_relation}
— never 'llm-interpretation' (interpretation is a separate layer).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from datetime import datetime as _dt

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import PriceHistory, Stock
from app.models.exchange_rate import ExchangeRate
from app.models.macro_factor import MacroFactor
from app.models.relation import StockRelation
from app.services.analyst import get_analyst_adapter, indicators


async def get_indicators(ticker: str) -> dict:
    """Compute RSI/MFI/ATR/CMF/OBV/MA/RVOL from latest 90 days OHLCV."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}'을(를) 찾을 수 없습니다."}

        since = date.today() - timedelta(days=120)
        rows = (
            await db.execute(
                select(PriceHistory)
                .where(PriceHistory.stock_id == stock.id, PriceHistory.date >= since)
                .order_by(PriceHistory.date.asc())
            )
        ).scalars().all()
        if len(rows) < 30:
            return {
                "error": "지표 계산에 필요한 가격 데이터 부족 (30일 미만)",
                "rows_available": len(rows),
            }

        closes = [r.close for r in rows]
        highs = [r.high for r in rows]
        lows = [r.low for r in rows]
        vols = [float(r.volume or 0) for r in rows]

        return {
            "ticker": ticker,
            "rsi_14": indicators.rsi(closes, 14),
            "atr_pct": indicators.atr_pct(highs, lows, closes, 14),
            "ma_stack": indicators.ma_stack(closes),
            "rvol_20": indicators.rvol(vols, 20),
            "obv_ratio": indicators.obv_ratio(closes, vols, 20),
            "cmf_20": indicators.cmf(highs, lows, closes, vols, 20),
            "lookback_days": len(rows),
            "citations": [
                {
                    "source_type": "db",
                    "label": f"DB · price_history ({rows[0].date}~{rows[-1].date})",
                }
            ],
        }


async def get_relations(ticker: str, relation_type: str | None = None) -> dict:
    """Read cached ontology relations for a stock. Caller can filter by type."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"relations": [], "error": f"종목 '{ticker}' 없음"}

        stmt = select(StockRelation).where(StockRelation.from_stock_id == stock.id)
        if relation_type:
            stmt = stmt.where(StockRelation.relation_type == relation_type)
        rows = (await db.execute(stmt)).scalars().all()

        # Resolve target tickers to names if they're stocks
        targets = {}
        target_tickers = [r.to_target for r in rows if r.to_kind == "stock"]
        if target_tickers:
            target_stocks = (
                await db.execute(
                    select(Stock).where(Stock.ticker.in_(target_tickers))
                )
            ).scalars().all()
            targets = {s.ticker: s for s in target_stocks}

        relations = []
        for r in rows:
            target_stock = targets.get(r.to_target)
            relations.append(
                {
                    "target_ticker": r.to_target,
                    "target_name": target_stock.name if target_stock else r.to_target,
                    "to_kind": r.to_kind,
                    "relation_type": r.relation_type,
                    "strength": r.strength,
                    "today_change_pct": (
                        target_stock.change_percent if target_stock else None
                    ),
                    "notes": r.notes,
                    "refreshed_at": r.refreshed_at.isoformat(),
                }
            )

        return {
            "ticker": ticker,
            "relation_type": relation_type,
            "relations": relations,
            "citations": [
                {
                    "source_type": "curated_relation",
                    "label": f"AI 큐레이션 · stock_relations cache (refreshed {rows[0].refreshed_at.date() if rows else 'n/a'})",
                }
            ]
            if rows
            else [],
        }


async def get_investor_flow(ticker: str) -> dict:
    """KR-only: foreign + institutional net flow over 5 days. Returns note for US."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}' 없음"}
        if stock.market not in ("KOSPI", "KOSDAQ", "KRX"):
            return {"ticker": ticker, "note": "kr-only", "flow": []}

        # P1 stub — actual KRX scrape lives in collectors/investor_flow.py.
        # Returning empty list keeps the tool contract; collector backfills.
        return {
            "ticker": ticker,
            "flow": [],
            "note": "investor flow collector not yet seeded — empty by design",
            "citations": [],
        }


async def get_macro_context() -> dict:
    """Return latest snapshot of macro factors plus upcoming events placeholder.

    Sources:
      - `macro_factors` table — VIX, US10Y, sector ETF closes (FRED collector
        seeds these; empty for now, fills as collector matures).
      - `exchange_rates` table — currency_pair → rate (sync_exchange_rates
        seeds USD/KRW, JPY/KRW etc. nightly).
    """
    async with async_session() as db:
        macro_rows = (
            await db.execute(
                select(MacroFactor).order_by(MacroFactor.date.desc())
            )
        ).scalars().all()

        latest: dict[str, tuple[float, date]] = {}
        for r in macro_rows:
            if r.factor not in latest:
                latest[r.factor] = (r.value, r.date)

        # ExchangeRate: latest per currency_pair (e.g. "USD/KRW").
        fx_rows = (
            await db.execute(
                select(ExchangeRate).order_by(ExchangeRate.date.desc())
            )
        ).scalars().all()
        latest_fx: dict[str, tuple[float, date]] = {}
        for r in fx_rows:
            if r.currency_pair not in latest_fx:
                latest_fx[r.currency_pair] = (r.rate, r.date)

        # Merge fx into the macro fx_pairs view. macro_factors fx entries
        # ("USD/KRW" inside MacroFactor) lose to exchange_rates if both present.
        fx_pairs: dict[str, float] = {
            k: v[0] for k, v in latest.items() if "/" in k
        }
        for pair, (rate, _dt) in latest_fx.items():
            fx_pairs[pair] = rate

        all_dates: list[date] = [v[1] for v in latest.values()] + [
            v[1] for v in latest_fx.values()
        ]
        latest_dt = max(all_dates, default=None)
        has_data = bool(latest) or bool(latest_fx)

        return {
            "vix": latest.get("VIX", (None, None))[0],
            "us_10y": latest.get("US10Y", (None, None))[0],
            "fx_pairs": fx_pairs,
            "sector_etfs": {
                k: v[0] for k, v in latest.items() if k in {"XLK", "XLF", "XLE"}
            },
            "upcoming_events": [],  # populated by web_search in research stage
            "citations": (
                [
                    {
                        "source_type": "market_data",
                        "label": (
                            f"DB · macro_factors + exchange_rates (latest "
                            f"as of {latest_dt or 'n/a'})"
                        ),
                    }
                ]
                if has_data
                else []
            ),
        }


async def web_search(query: str, max_results: int = 5, recency_days: int = 30) -> dict:
    """Tavily search. LLM picks `query` per analysis (no fixed keywords)."""
    if not settings.tavily_api_key:
        return {"results": [], "error": "tavily_api_key not set"}

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_raw_content": False,
        "days": recency_days,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {"results": [], "error": f"tavily error: {e}"}

    results = []
    for r in data.get("results", []):
        results.append(
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "snippet": r.get("content"),
                "published_at": r.get("published_date"),
            }
        )

    return {
        "query": query,
        "results": results,
        "citations": [
            {
                "source_type": "web",
                "label": f"web 검색 · '{query}'",
                "url": r["url"],
            }
            for r in results
        ],
    }


_NEWS_CLASSIFY_PROMPT = """\
다음 뉴스 항목들을 분류한다. 각 item에 대해:
- topic: earnings | macro | regulation | M&A | product | other
- sentiment: positive | neutral | negative
- impact: positive | mixed | neutral | negative

JSON으로만 응답:
{"items": [{"index": 0, "topic": "...", "sentiment": "...", "impact": "..."}, ...]}
"""


_DISCOVER_RELATIONS_PROMPT = """\
종목 {ticker}({name})에 대한 ontology 관계를 발견한다.
요청 타입: {types}.
- peer: 같은 사업 영역 직접 경쟁/대체
- supply_upstream: 본 종목이 공급받는 곳 (e.g. 칩 설계 → 파운드리)
- supply_downstream: 본 종목 공급의 수요처
- group: 같은 기업집단/지배구조
- theme: 함께 묶이는 내러티브 (AI, EV, biosimilar 등)

JSON으로만:
{{"relations": [{{"target_ticker": "...", "to_kind": "stock|theme", "relation_type": "...", "strength": 0..1, "notes": "..."}}, ...]}}

확신 없으면 빈 배열. 추측 금지.
"""


async def llm_classify_news(items: list[dict]) -> dict:
    """Classify a batch of news items with topic/sentiment/impact."""
    if not items:
        return {"items": []}
    payload = "\n".join(
        f"{i}. [{it.get('title', '')}] {it.get('summary', '')[:200]}"
        for i, it in enumerate(items)
    )
    prompt = _NEWS_CLASSIFY_PROMPT + "\n\n뉴스:\n" + payload
    adapter = get_analyst_adapter()
    try:
        raw = await adapter.generate_json(prompt)
        return json.loads(raw)
    except Exception as e:
        return {"items": [], "error": f"llm error: {e}"}


async def llm_discover_relations(
    ticker: str, relation_types: list[str] | None = None
) -> dict:
    """LLM curates relations for a stock; writes to stock_relations cache."""
    relation_types = relation_types or [
        "peer", "supply_upstream", "supply_downstream", "group", "theme"
    ]
    ticker = ticker.strip().upper()

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}' 없음"}

        prompt = _DISCOVER_RELATIONS_PROMPT.format(
            ticker=ticker, name=stock.name, types=", ".join(relation_types)
        )
        adapter = get_analyst_adapter()
        try:
            raw = await adapter.generate_json(prompt)
            result = json.loads(raw)
        except Exception as e:
            return {"written": 0, "error": f"llm error: {e}"}

        written = 0
        for rel in result.get("relations", []):
            target = rel.get("target_ticker") or rel.get("target") or ""
            if not target:
                continue
            target = target.strip().upper()
            existing = (
                await db.execute(
                    select(StockRelation).where(
                        StockRelation.from_stock_id == stock.id,
                        StockRelation.to_target == target,
                        StockRelation.relation_type == rel.get("relation_type", "peer"),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.strength = float(rel.get("strength", 0.5))
                existing.notes = rel.get("notes")
                existing.refreshed_at = _dt.utcnow()
            else:
                db.add(
                    StockRelation(
                        from_stock_id=stock.id,
                        to_target=target,
                        to_kind=rel.get("to_kind", "stock"),
                        relation_type=rel.get("relation_type", "peer"),
                        strength=float(rel.get("strength", 0.5)),
                        notes=rel.get("notes"),
                        source="llm-curation",
                        refreshed_at=_dt.utcnow(),
                    )
                )
            written += 1
        await db.commit()
        return {
            "ticker": ticker,
            "written": written,
            "citations": [
                {"source_type": "curated_relation", "label": f"AI 큐레이션 · {ticker}"}
            ],
        }


# === Tool registry & dispatcher (consumed by Stage 1 research agent) ===

# Re-export Phase A chat tools for the research agent.
from app.services.chat.tools import (  # noqa: E402
    get_recent_disclosures,
    get_recent_news,
    get_stock_snapshot,
)


RESEARCH_TOOL_FUNCTIONS = {
    "get_stock_snapshot": get_stock_snapshot,
    "get_recent_news": get_recent_news,
    "get_recent_disclosures": get_recent_disclosures,
    "get_indicators": get_indicators,
    "get_relations": get_relations,
    "get_macro_context": get_macro_context,
    "get_investor_flow": get_investor_flow,
    "web_search": web_search,
    "llm_classify_news": llm_classify_news,
    "llm_discover_relations": llm_discover_relations,
}


RESEARCH_TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_stock_snapshot",
        "description": "종목 기본 + 현재가 + 최신 재무. 시계열 X.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_recent_news",
        "description": "최근 N일 뉴스 + 본문 일부 + URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "default": 7},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_recent_disclosures",
        "description": "공시 (DART/SEC) 최근 N일.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "default": 30},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_indicators",
        "description": "RSI/ATR/MA/RVOL/OBV/CMF 계산값.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_relations",
        "description": "캐시된 ontology 관계. 비어있으면 llm_discover_relations 권장.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "relation_type": {
                    "type": "string",
                    "enum": [
                        "peer",
                        "supply_upstream",
                        "supply_downstream",
                        "group",
                        "theme",
                        "macro",
                    ],
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_macro_context",
        "description": "VIX/US10Y/USD/KRW/섹터 ETF 최신 스냅샷.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_investor_flow",
        "description": "KR 한정 외국인/기관 순매매 (5일 기준).",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "web_search",
        "description": (
            "Tavily 웹 검색. 키워드 자유 — 미래 재료 확인에 사용: 상장 예정/IPO, "
            "대형 계약, 파트너십, 고객 채택, 제품 출시, 규제 승인, 비상장 파트너."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
                "recency_days": {"type": "integer", "default": 30},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "llm_classify_news",
        "description": "뉴스 배치 → topic/sentiment/impact 라벨링.",
        "parameters": {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "object"}}},
            "required": ["items"],
        },
    },
    {
        "type": "function",
        "name": "llm_discover_relations",
        "description": "관계 캐시 stale일 때 LLM이 새로 발견. 결과는 stock_relations에 저장.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "relation_types": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["ticker"],
        },
    },
]


async def dispatch_research_tool(name: str, args: dict) -> dict:
    fn = RESEARCH_TOOL_FUNCTIONS.get(name)
    if not fn:
        return {"error": f"unknown tool: {name}"}
    try:
        return await fn(**args)
    except TypeError as e:
        return {"error": f"tool argument mismatch: {e}"}
    except Exception as e:
        return {"error": f"tool failure: {e}"}
