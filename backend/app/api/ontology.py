"""Ontology graph API (P3) — N-hop subgraph for the stock universe view.

Returns a JSON shape ready for `react-force-graph-2d`:
  { center: ticker, nodes: [{id, ticker, name, market, sector, tier, ...}],
    links: [{source, target, relation_type, signal_direction, confidence,
             strength, source_label, source_url}] }

Plan: docs/superpowers/plans/2026-04-28-ontology-aware-stock-card-implementation.md §19
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.markets import KR_MARKETS, US_MARKETS
from app.models import RelationCandidate, Stock, StockRelation
from app.services.ontology.evidence import (
    has_target_evidence,
    is_llm_source,
    rationale_admits_no_relationship,
)
from app.services.ontology.public_aliases import resolve_public_alias

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ontology", tags=["ontology"])

_MAX_NODES = 200
_DEFAULT_DEPTH = 1
_DEFAULT_TOP_N = 15  # per-node neighbor cap — 약한 sector_match가 카드를 도배하지 않게.
# 2026-05-15 — sector_match (0.4) 자동 제외. 데이터 quality 확보된 source 만.
_DEFAULT_MIN_CONFIDENCE = 0.5
_CONTEXT_MIN_CONFIDENCE = 0.35

BUSINESS_RELATION_TYPES = {
    "competitor",
    "contract_supplier",
    "contract_customer",
    "complementary",
    "supply_upstream",
    "supply_downstream",
    "regulatory_link",
}
CONTEXT_RELATION_TYPES = {"peer", "group", "theme", "macro"}
GraphView = Literal["business", "all"]


@router.get("/graph")
async def get_subgraph(
    ticker: str = Query(..., description="중심 종목 ticker"),
    depth: int = Query(_DEFAULT_DEPTH, ge=1, le=2, description="hop 수 1~2"),
    view: GraphView = Query(
        "business",
        description="business=사업 관계만, all=동종업계/테마/매크로 참고 관계 포함",
    ),
    sources: str | None = Query(
        None,
        description="콤마 구분 source 필터 (sector_match,sec_8k,news,dart_contract). 미지정 = 모두",
    ),
    min_confidence: float | None = Query(
        None,
        ge=0,
        le=1,
        description="confidence 하한. 미지정 시 business=0.5, all=0.35",
    ),
    cap: int = Query(_MAX_NODES, ge=10, le=400, description="노드 개수 총 cap"),
    top_n: int = Query(_DEFAULT_TOP_N, ge=3, le=50, description="노드별 최강 N개만"),
) -> dict:
    """Return a {nodes, links} subgraph centered on `ticker`."""
    source_filter = (
        {s.strip() for s in sources.split(",") if s.strip()}
        if sources
        else None
    )
    effective_min_confidence = _effective_min_confidence(min_confidence, view)
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
        virtual_nodes: dict[str, dict] = {}
        edges: list[dict] = []

        # BFS up to depth — frontier expands outward, capped at `cap` total nodes.
        frontier: list[Stock] = [center]
        hallucination_ids: list[int] = []
        for _hop in range(depth):
            next_frontier: list[Stock] = []
            for stock in frontier:
                rels = await _outgoing(
                    session, stock.id, source_filter,
                    effective_min_confidence, top_n, view,
                )
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
                    # Defense in depth (2026-05-14 SK하이닉스→동화약품 사례).
                    # LLM source 인데 rationale 에 target 증거 없으면 환상으로
                    # 간주 — 그래프에서 hide + soft-delete (다음 fetch 부터 query
                    # is_active=True 필터로 자연스럽게 제외).
                    if is_llm_source(r.source):
                        md = r.extra_metadata or {}
                        rationale = md.get("rationale") if isinstance(md, dict) else None
                        target_name = target_stock.name if target_stock else r.to_target
                        if rationale_admits_no_relationship(rationale):
                            hallucination_ids.append(r.id)
                            logger.warning(
                                "graph hide+soft-delete self-negating: "
                                "%s→%s src=%s rationale=%r",
                                stock.ticker, r.to_target, r.source,
                                (rationale or "")[:120],
                            )
                            continue
                        if not has_target_evidence(rationale, target_name, r.to_target):
                            hallucination_ids.append(r.id)
                            logger.warning(
                                "graph hide+soft-delete hallucination: "
                                "%s→%s src=%s rationale=%r",
                                stock.ticker, r.to_target, r.source,
                                (rationale or "")[:80],
                            )
                            continue
                    edges.append(_link_dict(stock, r, target_stock))
                    if target_stock is None:
                        virtual_nodes.setdefault(r.to_target, _virtual_node_dict(r))
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
        nodes.extend(virtual_nodes.values())

        # Fire-and-forget soft-delete — response 지연 X.
        if hallucination_ids:
            import asyncio as _asyncio

            _asyncio.create_task(_soft_delete_graph_relations(hallucination_ids))
    return {"center": center.ticker, "nodes": nodes, "links": edges}


async def _soft_delete_graph_relations(ids: list[int]) -> None:
    """Read-time 환상 감지된 row 들을 별도 세션에서 is_active=False 로 mark."""
    from sqlalchemy import update

    try:
        async with async_session() as db:
            await db.execute(
                update(StockRelation)
                .where(StockRelation.id.in_(ids))
                .values(is_active=False)
            )
            await db.commit()
        logger.info("graph soft-deleted %d hallucination relations: %s", len(ids), ids)
    except Exception as e:  # noqa: BLE001
        logger.warning("graph soft-delete relations failed for %s: %s", ids, e)


def _market_region(market: str | None) -> str:
    if market in KR_MARKETS:
        return "KR"
    if market in US_MARKETS:
        return "US"
    return "OTHER"


async def _outgoing(
    session: AsyncSession,
    from_id: int,
    source_filter: set[str] | None,
    min_conf: float,
    top_n: int,
    view: GraphView,
) -> list[StockRelation]:
    """cross-market 우선 + same-market 보완으로 top_n. 그래프가 KR/US 균형있게
    표시되도록. (이전: confidence × strength DESC만 → KR sector_match가
    top_n을 다 차지하고 cross-market US 노드가 0개 되는 버그)
    """
    stock_row = (
        await session.execute(
            select(Stock.ticker, Stock.market).where(Stock.id == from_id)
        )
    ).one_or_none()
    if stock_row is None:
        return []
    from_ticker, from_market = stock_row
    from_region = _market_region(from_market)
    cross_targets = US_MARKETS if from_region == "KR" else KR_MARKETS
    same_targets = KR_MARKETS if from_region == "KR" else US_MARKETS

    def _base():
        q = (
            select(StockRelation)
            .where(
                StockRelation.from_stock_id == from_id,
                StockRelation.is_active.is_(True),
                StockRelation.confidence >= min_conf,
            )
            .order_by((StockRelation.confidence * StockRelation.strength).desc())
        )
        if source_filter:
            q = q.where(StockRelation.source.in_(source_filter))
        return q

    rels = [
        r for r in (await session.execute(_base().limit(top_n * 6))).scalars().all()
        if _relation_allowed_for_view(r, view)
    ]
    rels.extend(
        await _private_candidate_edges(
            session, from_ticker, source_filter, min_conf, top_n, view
        )
    )
    if not rels:
        return []

    target_tickers = [r.to_target for r in rels]
    target_stocks = (
        await session.execute(select(Stock).where(Stock.ticker.in_(target_tickers)))
    ).scalars().all()
    target_by_ticker = {s.ticker: s for s in target_stocks}

    def _score(rel: StockRelation) -> float:
        return rel.confidence * rel.strength

    cross: list[StockRelation] = []
    same: list[StockRelation] = []
    virtual: list[StockRelation] = []
    for rel in rels:
        target = target_by_ticker.get(rel.to_target)
        if target is None:
            virtual.append(rel)
            continue
        if target.market in cross_targets:
            cross.append(rel)
        elif target.market in same_targets:
            same.append(rel)
        else:
            virtual.append(rel)

    cross.sort(key=_score, reverse=True)
    same.sort(key=_score, reverse=True)
    virtual.sort(key=_score, reverse=True)

    # cross-market relations 먼저 (절반 + 1 reserved)
    cross_cap = max(1, top_n // 2)
    picked = cross[:cross_cap]

    remaining = top_n - len(picked)
    if remaining <= 0:
        return picked
    # Private/theme targets are not expandable, but they are often the missing
    # business answer (OpenAI, SpaceX, AI theme). Reserve a small lane for them
    # before same-market peers fill the graph.
    virtual_cap = min(len(virtual), max(1, top_n // 4), remaining)
    if virtual_cap > 0:
        picked.extend(virtual[:virtual_cap])

    remaining = top_n - len(picked)
    if remaining > 0:
        picked.extend(same[:remaining])
    return picked


async def _private_candidate_edges(
    session: AsyncSession,
    from_ticker: str,
    source_filter: set[str] | None,
    min_conf: float,
    top_n: int,
    view: GraphView,
) -> list[SimpleNamespace]:
    """Expose high-confidence private RelationCandidate rows as graph-only edges.

    Knowledge extraction intentionally buffers non-public entities in
    RelationCandidate instead of StockRelation. The business graph still needs
    to show those influential private nodes, but only as read-time virtual
    edges so the promotion pipeline remains reserved for real listed stocks.
    """
    q = (
        select(RelationCandidate)
        .where(
            RelationCandidate.from_ticker == from_ticker,
            RelationCandidate.promoted_at.is_(None),
            RelationCandidate.confidence >= min_conf,
        )
        .order_by((RelationCandidate.confidence * RelationCandidate.strength).desc())
        .limit(top_n)
    )
    if source_filter:
        q = q.where(RelationCandidate.source.in_(source_filter))

    candidates = (await session.execute(q)).scalars().all()
    edges: list[SimpleNamespace] = []
    for cand in candidates:
        md = dict(cand.extra_metadata or {})
        alias = resolve_public_alias(md.get("target_name"), cand.to_ticker)
        to_target = cand.to_ticker
        if alias is not None:
            to_target = alias.parent_ticker
            md.update({
                "target_is_public": True,
                "resolved_parent_ticker": alias.parent_ticker,
                "resolved_parent_name": alias.parent_name,
                "target_entity_kind": alias.entity_kind,
            })

        if md.get("target_is_public") is not False:
            if alias is None:
                continue
        if not _relation_allowed_for_view(cand, view):
            continue
        edges.append(
            SimpleNamespace(
                id=-cand.id,
                to_target=to_target,
                to_kind="stock",
                relation_type=cand.relation_type,
                signal_direction=cand.signal_direction,
                strength=cand.strength if cand.strength is not None else 0.5,
                confidence=cand.confidence if cand.confidence is not None else 0.5,
                source=cand.source or "relation_candidate",
                source_url=cand.source_url,
                extra_metadata=md,
                is_candidate=True,
            )
        )
    return edges


def _effective_min_confidence(
    min_confidence: float | None,
    view: GraphView,
) -> float:
    if min_confidence is not None:
        return min_confidence
    return _CONTEXT_MIN_CONFIDENCE if view == "all" else _DEFAULT_MIN_CONFIDENCE


def _relation_allowed_for_view(rel: StockRelation, view: GraphView) -> bool:
    if view == "all":
        return True
    return rel.relation_type in BUSINESS_RELATION_TYPES


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
        "node_kind": "stock",
        "is_virtual": False,
    }


def _virtual_node_dict(rel: StockRelation) -> dict:
    md = rel.extra_metadata or {}
    node_kind = (
        "theme"
        if rel.relation_type == "theme" or getattr(rel, "to_kind", None) == "theme"
        else "macro"
        if rel.relation_type == "macro" or getattr(rel, "to_kind", None) == "macro"
        else "private"
    )
    name = md.get("target_name") or rel.to_target
    return {
        "id": rel.to_target,
        "ticker": rel.to_target,
        "name": name,
        "market": "PRIVATE" if node_kind == "private" else node_kind.upper(),
        "sector": None,
        "tier": 3,
        "is_center": False,
        "today_change_pct": None,
        "node_kind": node_kind,
        "is_virtual": True,
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
        "src_url": md.get("source_url") or getattr(rel, "source_url", None),
        "rationale": md.get("rationale"),
        "target_in_universe": tgt is not None,
    }
