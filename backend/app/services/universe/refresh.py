"""Nightly universe refresh (P1.7 Phase B).

매일 새벽 (KR 시장 open 전) 호출 — Tier 1 진입/탈락 처리.
seed와 동일하게 KR (dartlab listing) + US (S&P 500) fetch 후 bulk upsert.
fresh fetch에 없는 자동 출처 Tier 1 row는 Tier 2로 강등 (dropout).

`universe_source` 화이트리스트 — auto-fetch 출처만 강등 대상:
  - "kospi_listing" / "kosdaq_listing" / "sp500_index"

`user_promoted`, `seed_legacy`, manual 출처는 강등 보존 (사용자 의도 우선).

Plan: docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md §9
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §3.1
"""
from __future__ import annotations

import logging

from sqlalchemy import func, update

from app.database import async_session
from app.models.stock import Stock
from app.services.universe.seed_kr import (
    KR_KOSDAQ_SOURCE,
    KR_KOSPI_SOURCE,
    fetch_kr_universe,
)
from app.services.universe.seed_us import US_SP500_SOURCE, fetch_us_universe
from app.services.universe.upsert import (
    TIER_REFERENCE,
    TIER_USER_TOUCHED,
    bulk_upsert_tier1,
    dedupe_by_ticker,
)

logger = logging.getLogger(__name__)

_AUTO_FETCH_SOURCES = (KR_KOSPI_SOURCE, KR_KOSDAQ_SOURCE, US_SP500_SOURCE)
_DEMOTED_SOURCE = "demoted_dropout"


async def nightly_universe_refresh() -> dict:
    """Daily KR + S&P 500 refresh. Tier 1 진입/탈락 자동 처리.

    Fetch 실패 (둘 다 0 rows)면 skip — 전체 universe 일괄 demote 방지.
    한쪽만 실패해도 다른 쪽은 정상 처리 (KR 실패 시 US만 refresh).
    """
    kr_rows = await fetch_kr_universe()
    us_rows = await fetch_us_universe()
    fresh = dedupe_by_ticker(kr_rows + us_rows)

    if not fresh:
        logger.warning(
            "nightly_universe_refresh: 0 rows fetched — skipping to avoid mass demote"
        )
        return {"fetched": 0, "upserted": 0, "demoted": 0}

    upserted = await bulk_upsert_tier1(fresh)
    demoted = await _demote_dropouts({r.ticker for r in fresh})

    summary = {
        "fetched": len(fresh),
        "kr": len(kr_rows),
        "us": len(us_rows),
        "upserted": upserted,
        "demoted": demoted,
    }
    logger.info("nightly_universe_refresh: %s", summary)
    return summary


async def _demote_dropouts(fresh_tickers: set[str]) -> int:
    """Tier 1 row 중 fresh universe에서 빠진 자동 출처 row를 Tier 2로 강등.

    `universe_source` 화이트리스트를 통과하는 row만 대상 — `user_promoted`,
    `seed_legacy`, manual 출처는 보존.
    """
    if not fresh_tickers:
        return 0

    async with async_session() as db:
        stmt = (
            update(Stock)
            .where(
                Stock.tier == TIER_REFERENCE,
                Stock.ticker.notin_(fresh_tickers),
                Stock.universe_source.in_(_AUTO_FETCH_SOURCES),
            )
            .values(
                tier=TIER_USER_TOUCHED,
                tier_updated_at=func.now(),
                universe_source=_DEMOTED_SOURCE,
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount or 0
