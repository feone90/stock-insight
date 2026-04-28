"""Tools exposed to the v2 research agent (Stage 1).

Each tool returns dict with `citations` populated. Citations have
source_type from {db, market_data, news, disclosure, web, curated_relation}
— never 'llm-interpretation' (interpretation is a separate layer).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.database import async_session
from app.models import PriceHistory, Stock
from app.models.relation import StockRelation
from app.services.analyst import indicators


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
