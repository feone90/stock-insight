"""Regulatory co-shock relations (Codex H, 2026-05-14).

같은 political_signal 에 동시 노출된 종목들 사이에 자동으로 regulatory_link
edge 생성. 트럼프 "중국 60% 관세 부과" 같은 정책 이벤트에 NVDA / AMD /
005930 등이 동시 영향이면 그들 사이 regulatory pair edges 생성.

LLM 호출 0 — 기존 `political_signal_tickers` (1:N matching from Trump
statement analyzer) 데이터 재활용. 새 edge 만들기만.

source = 'political_coshock'. signal_direction 은 발언의 overall_sentiment
따라: bearish → negative, bullish → positive, mixed/inverse → inverse.
strength = 1.0 (동일 이벤트 동시 노출). confidence = signal LLM 분석
confidence 평균.

project_ontology_codex_review_2026_05_14 §우선순위 H.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Stock
from app.models.political_signal import PoliticalSignal, PoliticalSignalTicker
from app.services.ontology.upsert import bulk_upsert_relations

logger = logging.getLogger(__name__)

_SOURCE = "political_coshock"
_RELATION = "regulatory_link"
_DEFAULT_WINDOW_DAYS = 60
_MIN_TICKER_CONFIDENCE = 0.5
# co-shock pair 가 폭발하지 않도록. 한 signal 에 10+ ticker 가 매핑되면
# C(10,2)×2 = 90 rows 인데 macro shock 은 그 정도 spread 정상.
_MAX_TICKERS_PER_SIGNAL = 20


def _signal_direction_from_sentiment(sentiment: str | None) -> str:
    if sentiment == "bearish":
        return "negative"
    if sentiment in ("mixed", "inverse"):
        return "inverse"
    return "positive"


async def extract_regulatory_coshock(
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    min_signal_confidence: float = _MIN_TICKER_CONFIDENCE,
    session: AsyncSession | None = None,
) -> dict:
    """political_signals → regulatory_link edges upsert.

    Returns: {signals_seen, signals_used, pair_rows, upserted}.
    """
    cutoff = datetime.utcnow() - timedelta(days=window_days)

    if session is not None:
        return await _run(session, cutoff, min_signal_confidence)
    async with async_session() as own:
        summary = await _run(own, cutoff, min_signal_confidence)
        await own.commit()
        return summary


async def _run(
    session: AsyncSession, cutoff: datetime, min_conf: float
) -> dict:
    signals = (
        await session.execute(
            select(PoliticalSignal).where(
                PoliticalSignal.is_market_relevant.is_(True),
                PoliticalSignal.analyzed_at.isnot(None),
                PoliticalSignal.posted_at >= cutoff,
                # Defense-in-depth: 5/13 commit `b00fc15` 와 동일 — sample_macro
                # 잔재 재유입돼도 가짜 regulatory edge 생성 차단.
                PoliticalSignal.source != "sample_macro",
            )
        )
    ).scalars().all()

    if not signals:
        return {"signals_seen": 0, "signals_used": 0, "pair_rows": 0, "upserted": 0}

    rows: list[dict] = []
    signals_used = 0
    for sig in signals:
        impacts = (
            await session.execute(
                select(PoliticalSignalTicker).where(
                    PoliticalSignalTicker.signal_id == sig.id
                )
            )
        ).scalars().all()
        valid = [i for i in impacts if (i.confidence or 0) >= min_conf]
        if len(valid) < 2:
            continue
        valid.sort(key=lambda i: i.confidence or 0, reverse=True)
        valid = valid[:_MAX_TICKERS_PER_SIGNAL]

        tickers = list({i.ticker for i in valid})
        stock_rows = (
            await session.execute(
                select(Stock.id, Stock.ticker).where(Stock.ticker.in_(tickers))
            )
        ).all()
        ticker_to_id = {t: sid for sid, t in stock_rows}

        # ticker_to_id 안 매핑된 (universe 밖) ticker drop
        id_pairs = [
            (ticker_to_id[i.ticker], i.ticker)
            for i in valid
            if i.ticker in ticker_to_id
        ]
        if len(id_pairs) < 2:
            continue

        signals_used += 1
        direction = _signal_direction_from_sentiment(sig.overall_sentiment)
        avg_conf = sum(i.confidence or 0 for i in valid) / len(valid)
        avg_conf = max(0.0, min(1.0, avg_conf))

        rationale = (sig.summary_ko or "").strip()[:300] or (
            sig.content or ""
        ).strip()[:200]
        metadata = {
            "rationale": rationale,
            "source_url": sig.url,
            "macro_themes": sig.macro_themes or [],
            "posted_at": sig.posted_at.isoformat() if sig.posted_at else None,
        }

        for (id_a, t_a), (id_b, t_b) in combinations(id_pairs, 2):
            rows.append(
                {
                    "from_stock_id": id_a,
                    "to_target": t_b,
                    "to_kind": "stock",
                    "relation_type": _RELATION,
                    "strength": 1.0,
                    "source": _SOURCE,
                    "signal_direction": direction,
                    "confidence": avg_conf,
                    "metadata": metadata,
                }
            )
            rows.append(
                {
                    "from_stock_id": id_b,
                    "to_target": t_a,
                    "to_kind": "stock",
                    "relation_type": _RELATION,
                    "strength": 1.0,
                    "source": _SOURCE,
                    "signal_direction": direction,
                    "confidence": avg_conf,
                    "metadata": metadata,
                }
            )

    upserted = await bulk_upsert_relations(rows, session=session)
    summary = {
        "signals_seen": len(signals),
        "signals_used": signals_used,
        "pair_rows": len(rows),
        "upserted": upserted,
    }
    logger.info("regulatory_coshock: %s", summary)
    return summary
