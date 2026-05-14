"""환상 (hallucination) StockRelation row 들을 일괄 DELETE 하는 서비스.

호출처:
  - `app.main.lifespan` — 앱 startup 시 1회 자동 청소 (deploy 마다)
  - `app.api.admin.purge_ontology_noise` — admin 수동 트리거 (그 외 noise 와 함께)
  - 추후 scheduler 일일 cron 가능

이 함수는 **DELETE** 한다 (soft-delete 아님). read path 의 fire-and-forget
soft-delete (is_active=False) 와는 의도 다름:
  - read path soft-delete: 사용자 화면에 *지금 당장* 안 보이게 + 다음 fetch
    에서도 skip. is_active=False 유지하면 admin 이 복구도 가능.
  - 이 startup purge: 영구 삭제. DB 청소 + 디스크 회수.

사용자 피드백 (2026-05-14): "옛 row를 db에서 날리던가 정리를 하면되잖나" —
read 시점 hide 만으로는 부족, 실제로 row 가 사라져야 한다.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock, StockRelation
from app.services.ontology.evidence import (
    LLM_SOURCES_REQUIRING_EVIDENCE,
    has_target_evidence,
    rationale_admits_no_relationship,
)

logger = logging.getLogger(__name__)


async def purge_cross_market_sector_match(session: AsyncSession) -> int:
    """KR↔US cross-market sector_match peer row 일괄 삭제.

    2026-05-15 결정 — `sector_match` 가 GICS bucket 으로 cross-market peer
    만들던 룰 자체를 제거 (sector_match.py 의 2026-05-15 docstring 참조).
    옛 cross-market 페어 row 들은 deploy 마다 startup 시 청소.

    Example: MS (US/IT) ↔ 두산 (KR/IT) 같은 무의미 peer 가 사용자 관계도에
    "왜 한국 반도체가 여기?" 혼란만 유발. 직접 DB 청소.
    """
    rows = (
        await session.execute(
            select(
                StockRelation.id,
                StockRelation.from_stock_id,
                StockRelation.to_target,
            ).where(StockRelation.source == "sector_match")
        )
    ).all()

    if not rows:
        return 0

    # from_stock + to_target 의 market 한꺼번에 lookup.
    from_ids = {r.from_stock_id for r in rows}
    to_tickers = {r.to_target for r in rows if r.to_target}
    market_by_id: dict[int, str] = {}
    if from_ids:
        from_rows = (
            await session.execute(
                select(Stock.id, Stock.market).where(Stock.id.in_(from_ids))
            )
        ).all()
        market_by_id = {i: (m or "") for i, m in from_rows}
    market_by_ticker: dict[str, str] = {}
    if to_tickers:
        to_rows = (
            await session.execute(
                select(Stock.ticker, Stock.market).where(Stock.ticker.in_(to_tickers))
            )
        ).all()
        market_by_ticker = {t: (m or "") for t, m in to_rows}

    def _region(m: str) -> str:
        if m in ("KOSPI", "KOSDAQ"):
            return "KR"
        if m == "US":
            return "US"
        return "OTHER"

    bad_ids: list[int] = []
    for r in rows:
        from_region = _region(market_by_id.get(r.from_stock_id, ""))
        to_region = _region(market_by_ticker.get(r.to_target or "", ""))
        if from_region == "OTHER" or to_region == "OTHER":
            continue  # market 정보 불완전 — 보수적 보존
        if from_region != to_region:
            bad_ids.append(r.id)

    if not bad_ids:
        return 0
    await session.execute(
        delete(StockRelation).where(StockRelation.id.in_(bad_ids))
    )
    await session.commit()
    logger.info(
        "purge_cross_market_sector_match: deleted %d rows (sample=%s)",
        len(bad_ids), bad_ids[:5],
    )
    return len(bad_ids)


async def purge_self_negating_rationales(session: AsyncSession) -> int:
    """LLM 이 rationale 안에 "관계 없음" 자백한 row 영구 삭제.

    2026-05-15 발견: Beyond Meat 기사로 NVDA↔McDonald's complementary 박혔는데
    rationale 이 "NVDA와의 직접 관계는 없음" 명시. 자료가 자기 부정 — 100%
    환상. deploy 마다 startup 시 일괄 청소.
    """
    rows = (
        await session.execute(
            select(StockRelation.id, StockRelation.extra_metadata).where(
                StockRelation.source.in_(LLM_SOURCES_REQUIRING_EVIDENCE)
            )
        )
    ).all()
    if not rows:
        return 0

    bad_ids: list[int] = []
    for r in rows:
        meta = r.extra_metadata or {}
        rationale = meta.get("rationale") if isinstance(meta, dict) else None
        if rationale_admits_no_relationship(rationale):
            bad_ids.append(r.id)

    if not bad_ids:
        return 0
    await session.execute(
        delete(StockRelation).where(StockRelation.id.in_(bad_ids))
    )
    await session.commit()
    logger.info(
        "purge_self_negating_rationales: deleted %d rows (sample=%s)",
        len(bad_ids), bad_ids[:5],
    )
    return len(bad_ids)


async def purge_llm_hallucinations(session: AsyncSession) -> int:
    """LLM source row 중 rationale 에 target Stock.name / ticker substring 증거
    없는 것 영구 삭제. 삭제된 row 수 반환.

    필터:
        source ∈ LLM_SOURCES_REQUIRING_EVIDENCE
        AND NOT (Stock.name OR ticker substring in rationale)

    1자 이름/ticker 케이스 (Ford="F" 등) 는 evidence util 이 자동 우회 (가드
    무력화). production 에서 실수로 잡지 않음.
    """
    rows = (
        await session.execute(
            select(
                StockRelation.id,
                StockRelation.to_target,
                StockRelation.extra_metadata,
            ).where(StockRelation.source.in_(LLM_SOURCES_REQUIRING_EVIDENCE))
        )
    ).all()

    if not rows:
        return 0

    to_targets = {r.to_target for r in rows if r.to_target}
    name_map: dict[str, str] = {}
    if to_targets:
        name_rows = (
            await session.execute(
                select(Stock.ticker, Stock.name).where(Stock.ticker.in_(to_targets))
            )
        ).all()
        name_map = {t: (n or "") for t, n in name_rows}

    bad_ids: list[int] = []
    for r in rows:
        target_name = name_map.get(r.to_target or "", "")
        if not target_name:
            # universe 밖 — 다른 noise 필터에서 처리. 이 함수 책임 아님.
            continue
        meta = r.extra_metadata or {}
        rationale = meta.get("rationale") if isinstance(meta, dict) else None
        if not has_target_evidence(rationale, target_name, r.to_target):
            bad_ids.append(r.id)

    if not bad_ids:
        return 0

    await session.execute(
        delete(StockRelation).where(StockRelation.id.in_(bad_ids))
    )
    await session.commit()
    logger.info(
        "purge_llm_hallucinations: deleted %d rows (sample ids=%s)",
        len(bad_ids), bad_ids[:5],
    )
    return len(bad_ids)
