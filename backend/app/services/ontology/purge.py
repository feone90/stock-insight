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
)

logger = logging.getLogger(__name__)


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
