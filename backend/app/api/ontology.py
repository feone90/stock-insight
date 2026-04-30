"""Ontology graph API (P3) — N-hop subgraph for the stock universe view.

Returns a JSON shape ready for `react-force-graph-2d`:
  { center: ticker, nodes: [{id, ticker, name, market, sector, tier, ...}],
    links: [{source, target, relation_type, signal_direction, confidence,
             strength, source_label, source_url}] }

Plan: docs/superpowers/plans/2026-04-28-ontology-aware-stock-card-implementation.md §19
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Stock, StockRelation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ontology", tags=["ontology"])

_MAX_NODES = 200
_DEFAULT_DEPTH = 1
_DEFAULT_TOP_N = 15  # per-node neighbor cap — 약한 sector_match가 카드를 도배하지 않게.


@router.get("/graph")
async def get_subgraph(
    ticker: str = Query(..., description="중심 종목 ticker"),
    depth: int = Query(_DEFAULT_DEPTH, ge=1, le=2, description="hop 수 1~2"),
    sources: str | None = Query(
        None,
        description="콤마 구분 source 필터 (sector_match,sec_8k,news,dart_contract). 미지정 = 모두",
    ),
    min_confidence: float = Query(0.0, ge=0, le=1, description="confidence 하한"),
    cap: int = Query(_MAX_NODES, ge=10, le=400, description="노드 개수 총 cap"),
    top_n: int = Query(_DEFAULT_TOP_N, ge=3, le=50, description="노드별 최강 N개만"),
) -> dict:
    """Return a {nodes, links} subgraph centered on `ticker`."""
    source_filter = (
        {s.strip() for s in sources.split(",") if s.strip()}
        if sources
        else None
    )
    normalized = ticker.upper() if ticker.isalpha() else ticker
    async with async_session() as session:
        center = (
            await session.execute(
                select(Stock).where(Stock.ticker == normalized)
            )
        ).scalar_one_or_none()
        if center is None:
            raise HTTPException(404, f"종목 {ticker} 없음")

        seen_ids: set[int] = {center.id}
        seen_tickers: dict[str, Stock] = {center.ticker: center}
        edges: list[dict] = []

        # BFS up to depth — frontier expands outward, capped at `cap` total nodes.
        frontier: list[Stock] = [center]
        for _hop in range(depth):
            next_frontier: list[Stock] = []
            for stock in frontier:
                rels = await _outgoing(session, stock.id, source_filter, min_confidence, top_n)
                target_tickers = [r.to_target for r in rels]
                if not target_tickers:
                    continue
                target_stocks = (
                    await session.execute(
                        select(Stock).where(Stock.ticker.in_(target_tickers))
                    )
                ).scalars().all()
                target_by_ticker = {s.ticker: s for s in target_stocks}
                for r in rels:
                    target_stock = target_by_ticker.get(r.to_target)
                    edges.append(_link_dict(stock, r, target_stock))
                    if target_stock is None:
                        continue
                    if target_stock.id in seen_ids:
                        continue
                    if len(seen_ids) >= cap:
                        continue
                    seen_ids.add(target_stock.id)
                    seen_tickers[target_stock.ticker] = target_stock
                    next_frontier.append(target_stock)
            frontier = next_frontier
            if len(seen_ids) >= cap:
                break

        nodes = [_node_dict(s, is_center=s.id == center.id) for s in seen_tickers.values()]
    return {"center": center.ticker, "nodes": nodes, "links": edges}


async def _outgoing(
    session: AsyncSession,
    from_id: int,
    source_filter: set[str] | None,
    min_conf: float,
    top_n: int,
) -> list[StockRelation]:
    """confidence × strength DESC 순으로 top_n. 약한 sector_match로 그래프가
    쿠킹 도우(="구름") 모양 되는 걸 막음."""
    q = (
        select(StockRelation)
        .where(
            StockRelation.from_stock_id == from_id,
            StockRelation.is_active.is_(True),
            StockRelation.confidence >= min_conf,
        )
        .order_by((StockRelation.confidence * StockRelation.strength).desc())
        .limit(top_n)
    )
    if source_filter:
        q = q.where(StockRelation.source.in_(source_filter))
    return (await session.execute(q)).scalars().all()


def _node_dict(s: Stock, *, is_center: bool) -> dict:
    return {
        "id": s.ticker,
        "ticker": s.ticker,
        "name": s.name,
        "market": s.market,
        "sector": s.sector,
        "tier": s.tier,
        "is_center": is_center,
        "today_change_pct": s.change_percent,
    }


def _link_dict(src: Stock, rel: StockRelation, tgt: Stock | None) -> dict:
    md = rel.extra_metadata or {}
    return {
        "source": src.ticker,
        "target": rel.to_target,
        "relation_type": rel.relation_type,
        "signal_direction": rel.signal_direction or "positive",
        "strength": rel.strength,
        "confidence": rel.confidence,
        "src_label": rel.source,
        "src_url": md.get("source_url"),
        "target_in_universe": tgt is not None,
    }
