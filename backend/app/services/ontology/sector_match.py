"""Universe-wide bidirectional sector match (P1.6 v0).

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6.1
Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6.1

P1.5 `onto_hook.enrich_stock_after_register` only emits a single direction
edge (newly-registered → existing peer). v0 fixes both:
  - bidirectional rows (a→b and b→a)
  - applied across the entire Tier 1+2 universe in one nightly pass

Per-sector cap (`SECTOR_PAIR_CAP`) bounds explosion. KSIC is more fragmented
than GICS 11 so top sectors (소프트웨어, 특수목적 기계, 전자부품 ...) carry 100+
members; without cap a single sector emits C(189,2)×2 = ~35K rows. Cap 30 →
worst-case sector emits ~870 rows; total network sits in the ~30-60K range.

Cap ordering: market_cap DESC (NULLS LAST), then ticker ASC. Phase A leaves
market_cap=None for all KR rows so the tiebreaker (ticker ASC) is the
de-facto Phase A ordering — deterministic and stable across re-runs.

2026-05-15 cross-market 제거 (사용자 + Codex 시니어 product 리뷰):
같은 GICS sector 만으로 KR↔US peer 만드는 건 *비즈니스 관점* 무의미. MS
(IT) 가 두산/DB하이텍/그린광학 (KR IT) 과 "peer" 라는 표현은 사용자한테
"왜 한국 반도체가 여기?" 혼란만 야기. 핵심 가치는 same-market peer (예:
삼성전자 ↔ SK하이닉스 둘 다 메모리). Cross-market 매크로 노출은 별도
macro 섹션이 처리. 따라서 KR/US/OTHER 그룹 각자 내부 combinations 만.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Stock
from app.services.ontology.upsert import bulk_upsert_relations

logger = logging.getLogger(__name__)

SECTOR_PAIR_CAP = 50  # per market bucket — see _bucket_cap below
_TIER_USER_TOUCHED = 2
_PEER_SOURCE = "sector_match"
_PEER_RELATION = "peer"
_DEFAULT_STRENGTH = 0.5
_DEFAULT_CONFIDENCE = 0.4  # objective sector match — strong signal but not certainty

# KSIC (Korean industry codes, in Korean) → GICS 11 sector. Bridges KR/US so
# 005930("통신 및 방송 장비 제조업") groups with NVDA/AMD/AVGO under
# "Information Technology". Path is module-relative so it works regardless of
# CWD when run from scheduler / test fixtures.
_KSIC_GICS_PATH = Path(__file__).parent.parent.parent / "data" / "ksic_to_gics.json"
_ksic_to_gics: dict[str, str] | None = None


def _load_ksic_to_gics() -> dict[str, str]:
    global _ksic_to_gics
    if _ksic_to_gics is None:
        try:
            _ksic_to_gics = json.loads(_KSIC_GICS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("ksic_to_gics map load failed: %s — falling back to raw sector", e)
            _ksic_to_gics = {}
    return _ksic_to_gics


def _normalized_sector(stock: Stock) -> str | None:
    """Return the bridge key under which `stock` is grouped for cross-market match.

    KR (KOSPI/KOSDAQ) → KSIC mapped to GICS via the lookup; if the KSIC isn't
    in the map, fall back to the raw KSIC string (still groups within KR).
    US/other → raw sector (already GICS from S&P 500 wikipedia).
    """
    if not stock.sector or stock.sector == "Unknown":
        return None
    if stock.market in ("KOSPI", "KOSDAQ"):
        return _load_ksic_to_gics().get(stock.sector, stock.sector)
    return stock.sector


async def universe_wide_sector_match(
    *, session: AsyncSession | None = None
) -> dict:
    """Re-run the universe-wide sector cross-match.

    Idempotent — ON CONFLICT DO UPDATE in `bulk_upsert_relations` smooths
    re-runs (strength averaged, confidence MAX, refreshed_at bumped).
    Pass `session` to reuse caller transaction (test fixtures).
    """
    if session is not None:
        return await _run(session)
    async with async_session() as own:
        summary = await _run(own)
        await own.commit()
        return summary


async def _run(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Stock).where(
            Stock.tier <= _TIER_USER_TOUCHED,
            Stock.is_delisted.is_(False),
        )
    )
    stocks = result.scalars().all()

    by_sector: dict[str, list[Stock]] = defaultdict(list)
    for s in stocks:
        key = _normalized_sector(s)
        if key is None:
            continue
        by_sector[key].append(s)

    rows: list[dict] = []
    capped_sectors = 0
    for sector, members in by_sector.items():
        if len(members) < 2:
            continue
        kr = [m for m in members if m.market in ("KOSPI", "KOSDAQ")]
        us = [m for m in members if m.market == "US"]
        other = [m for m in members if m.market not in ("KOSPI", "KOSDAQ", "US")]

        kr_capped = _rank_and_cap(kr)
        us_capped = _rank_and_cap(us)
        other_capped = _rank_and_cap(other)
        if (
            len(kr) > SECTOR_PAIR_CAP
            or len(us) > SECTOR_PAIR_CAP
            or len(other) > SECTOR_PAIR_CAP
        ):
            capped_sectors += 1

        # Same-market only — 각 market bucket 안에서만 combinations.
        # KR↔US cross-market peer 는 의도적으로 안 만든다 (위 module docstring
        # 2026-05-15 결정 참조).
        for bucket in (kr_capped, us_capped, other_capped):
            for a, b in combinations(bucket, 2):
                rows.append(_make_peer_row(a, b))
                rows.append(_make_peer_row(b, a))

    upserted = await bulk_upsert_relations(rows, session=session)
    summary = {
        "stocks_in_universe": len(stocks),
        "sectors": len(by_sector),
        "sectors_capped": capped_sectors,
        "pair_rows": len(rows),
        "upserted": upserted,
    }
    logger.info("universe_wide_sector_match: %s", summary)
    return summary


def _rank_and_cap(members: list[Stock]) -> list[Stock]:
    """Tier-2 first (user-touched seeds), then market_cap DESC NULLS LAST,
    then ticker ASC. Truncate to `SECTOR_PAIR_CAP`."""
    ranked = sorted(
        members,
        key=lambda s: (
            0 if s.tier == 2 else 1,
            s.market_cap is None,
            -(float(s.market_cap) if s.market_cap is not None else 0.0),
            s.ticker,
        ),
    )
    return ranked[:SECTOR_PAIR_CAP]


def _make_peer_row(a: Stock, b: Stock) -> dict:
    return {
        "from_stock_id": a.id,
        "to_target": b.ticker,
        "to_kind": "stock",
        "relation_type": _PEER_RELATION,
        "strength": _DEFAULT_STRENGTH,
        "source": _PEER_SOURCE,
        "signal_direction": "positive",
        "confidence": _DEFAULT_CONFIDENCE,
    }
