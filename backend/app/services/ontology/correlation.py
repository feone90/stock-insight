"""Pairwise price correlation + inverse-signal verification (P1.6 v3).

`compute_pairwise_correlation` returns the pearson-correlation of log returns
for each ticker pair over a recent window. `verify_inverse_signals` walks the
LLM-extracted competitor / inverse rows in `stock_relations` and adjusts
their `confidence` based on whether the actual price series agrees:

  - corr ≤ -0.3 (strong inverse) → boost confidence (+0.1, capped at 1.0)
  - corr ≥ -0.1 (no inverse signal) → drop confidence (-0.2, floor at 0.1)
  - otherwise leave row alone

This catches LLM hallucinations cheap — corr is a DB-only computation.

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6.4.2
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import PriceHistory, Stock, StockRelation

logger = logging.getLogger(__name__)

_DEFAULT_WINDOW_DAYS = 90
_INVERSE_STRONG_CORR = -0.3  # below this → confirm
_INVERSE_WEAK_CORR = -0.1  # above this → contradict
_BOOST_DELTA = 0.1
_PENALTY_DELTA = 0.2
_CONFIDENCE_FLOOR = 0.1
_CONFIDENCE_CEIL = 1.0
_MIN_OBSERVATIONS = 20  # need ≥20 overlapping return days for a stable corr


async def compute_pairwise_correlation(
    tickers: Iterable[str],
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    session: AsyncSession | None = None,
) -> dict[tuple[str, str], float]:
    """Pearson correlation of daily log returns over the last `window_days`.

    Returns {(a, b): r} for every (a, b) where a < b (string-sort), only if
    both series have ≥ `_MIN_OBSERVATIONS` overlapping return days. Sparse /
    new-listing tickers silently skipped.
    """
    if session is not None:
        return await _compute(session, tickers, window_days)
    async with async_session() as own:
        return await _compute(own, tickers, window_days)


async def _compute(
    session: AsyncSession, tickers: Iterable[str], window_days: int
) -> dict[tuple[str, str], float]:
    ticker_list = sorted(set(tickers))
    if len(ticker_list) < 2:
        return {}

    cutoff = date.today() - timedelta(days=window_days)
    rows = (
        await session.execute(
            select(Stock.ticker, PriceHistory.date, PriceHistory.close)
            .join(PriceHistory, PriceHistory.stock_id == Stock.id)
            .where(
                Stock.ticker.in_(ticker_list),
                PriceHistory.date >= cutoff,
                PriceHistory.close > 0,
            )
            .order_by(Stock.ticker, PriceHistory.date)
        )
    ).all()

    by_ticker: dict[str, list[tuple[date, float]]] = {}
    for ticker, dt, close in rows:
        by_ticker.setdefault(ticker, []).append((dt, float(close)))

    returns_by_ticker: dict[str, dict[date, float]] = {}
    for ticker, series in by_ticker.items():
        rets: dict[date, float] = {}
        prev_close: float | None = None
        for dt, c in series:
            if prev_close is not None and prev_close > 0:
                rets[dt] = math.log(c / prev_close)
            prev_close = c
        if len(rets) >= _MIN_OBSERVATIONS:
            returns_by_ticker[ticker] = rets

    out: dict[tuple[str, str], float] = {}
    eligible = sorted(returns_by_ticker.keys())
    for i, a in enumerate(eligible):
        ra = returns_by_ticker[a]
        for b in eligible[i + 1:]:
            rb = returns_by_ticker[b]
            common = ra.keys() & rb.keys()
            if len(common) < _MIN_OBSERVATIONS:
                continue
            r = _pearson([ra[d] for d in common], [rb[d] for d in common])
            if r is not None:
                out[(a, b)] = r
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or not xs:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(vx * vy)
    if denom <= 0:
        return None
    return cov / denom


async def verify_inverse_signals(
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    session: AsyncSession | None = None,
) -> dict:
    """Walk inverse-direction relations, compute price corr, adjust confidence.

    Idempotent — running twice on the same data yields the same final state
    only if corr is unchanged. Confidence drift is symmetric (boost +0.1 once,
    penalty -0.2 once) so this should be a stabilising signal, not oscillatory.
    """
    if session is not None:
        return await _verify(session, window_days)
    async with async_session() as own:
        summary = await _verify(own, window_days)
        await own.commit()
        return summary


async def _verify(session: AsyncSession, window_days: int) -> dict:
    rows = (
        await session.execute(
            select(StockRelation, Stock.ticker)
            .join(Stock, Stock.id == StockRelation.from_stock_id)
            .where(StockRelation.signal_direction == "inverse")
        )
    ).all()
    if not rows:
        return {"checked": 0, "boosted": 0, "penalised": 0, "skipped": 0}

    pair_to_relations: dict[tuple[str, str], list[StockRelation]] = {}
    tickers: set[str] = set()
    for rel, from_ticker in rows:
        a, b = sorted((from_ticker, rel.to_target))
        pair_to_relations.setdefault((a, b), []).append(rel)
        tickers.add(from_ticker)
        tickers.add(rel.to_target)

    corrs = await _compute(session, tickers, window_days)

    boosted = 0
    penalised = 0
    skipped = 0
    for pair, rel_list in pair_to_relations.items():
        corr = corrs.get(pair)
        if corr is None:
            skipped += len(rel_list)
            continue
        if corr <= _INVERSE_STRONG_CORR:
            new_conf_delta = _BOOST_DELTA
            counter = "boost"
        elif corr >= _INVERSE_WEAK_CORR:
            new_conf_delta = -_PENALTY_DELTA
            counter = "penalty"
        else:
            skipped += len(rel_list)
            continue

        for rel in rel_list:
            new_conf = max(
                _CONFIDENCE_FLOOR,
                min(_CONFIDENCE_CEIL, rel.confidence + new_conf_delta),
            )
            await session.execute(
                update(StockRelation)
                .where(StockRelation.id == rel.id)
                .values(confidence=new_conf)
            )
            if counter == "boost":
                boosted += 1
            else:
                penalised += 1

    summary = {
        "checked": sum(len(v) for v in pair_to_relations.values()),
        "boosted": boosted,
        "penalised": penalised,
        "skipped": skipped,
        "pairs_with_corr": len(corrs),
    }
    logger.info("verify_inverse_signals: %s", summary)
    return summary
