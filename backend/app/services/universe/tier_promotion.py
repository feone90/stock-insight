"""Tier 3 → Tier 2 자동 승격 (P1.7 Phase B).

User가 종목을 검색/카드 view 또는 favorite 등록할 때 호출.
fire-and-forget 호출 권장 — endpoint latency 영향 0.

Plan: docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md §8
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §3.1
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import func, update

from app.database import async_session
from app.models.stock import Stock

logger = logging.getLogger(__name__)

_TIER_USER_TOUCHED = 2
_TIER_LATENT = 3
_USER_PROMOTED_SOURCE = "user_promoted"


async def promote_to_tier_2(stock_id: int) -> None:
    """Tier 3 → Tier 2 승격. tier=1 또는 2 row는 noop.

    own session 사용 — 호출자의 request session이 응답 후 닫혀도 안전.
    P1.6 머지 후 `scan_pending_candidates`를 fire-and-forget 트리거.
    """
    try:
        async with async_session() as db:
            stmt = (
                update(Stock)
                .where(Stock.id == stock_id, Stock.tier == _TIER_LATENT)
                .values(
                    tier=_TIER_USER_TOUCHED,
                    tier_updated_at=func.now(),
                    universe_source=_USER_PROMOTED_SOURCE,
                )
            )
            await db.execute(stmt)
            await db.commit()
    except Exception as e:  # noqa: BLE001 — fire-and-forget; never crash caller
        logger.warning("promote_to_tier_2(stock_id=%s) failed: %s", stock_id, e)
        return

    _trigger_pending_candidate_scan(stock_id)


def _trigger_pending_candidate_scan(stock_id: int) -> None:
    """P1.6 hook — relation_candidates buffer를 즉시 promote.

    P1.6이 머지되기 전에는 import error 발생. try/except로 graceful no-op.
    """
    try:
        from app.services.ontology.upsert import (  # type: ignore[import-not-found]
            scan_pending_candidates,
        )
    except ImportError:
        return
    try:
        asyncio.create_task(scan_pending_candidates(stock_id))
    except Exception as e:  # noqa: BLE001
        logger.warning("scan_pending_candidates trigger failed for %s: %s", stock_id, e)
