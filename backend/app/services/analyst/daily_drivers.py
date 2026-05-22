from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Analysis, Favorite, News, PriceHistory, Stock
from app.models.daily_driver import DailyPriceDriver
from app.schemas.daily_driver import DailyDriverRunResult, DailyPriceDriverResponse
from app.services.analyst import get_analyst_adapter
from app.services.analyst.cost import can_proceed

logger = logging.getLogger(__name__)

MODEL_VERSION = "daily_driver_v1"
_NEWS_LIMIT = 12
_BODY_LIMIT = 1200


async def run_daily_driver_batch(limit: int = 80) -> DailyDriverRunResult:
    """Create finalized drivers for each favorite stock's latest completed date."""
    if not can_proceed():
        return DailyDriverRunResult(
            status="skipped_budget", processed=0, created=0, skipped=0, errors=[]
        )

    async with async_session() as db:
        stocks = (
            await db.execute(
                select(Stock).join(Favorite, Favorite.stock_id == Stock.id).distinct().limit(limit)
            )
        ).scalars().all()

    processed = created = skipped = 0
    errors: list[str] = []
    rows: list[DailyPriceDriverResponse] = []
    for stock in stocks:
        try:
            async with async_session() as db:
                trade_date = await latest_completed_trade_date(db, stock.id)
                if trade_date is None:
                    skipped += 1
                    continue
                result = await ensure_daily_driver(db, stock, trade_date)
                processed += 1
                if result is None:
                    skipped += 1
                else:
                    created += 1
                    rows.append(_response(stock.ticker, result))
        except Exception as e:  # noqa: BLE001
            logger.exception("daily driver batch failed for %s: %s", stock.ticker, e)
            errors.append(f"{stock.ticker}: {e}")

    return DailyDriverRunResult(
        status="ok",
        processed=processed,
        created=created,
        skipped=skipped,
        errors=errors,
        rows=rows,
    )


async def backfill_daily_drivers(
    ticker: str | None = None,
    days: int = 30,
    limit: int = 80,
    force: bool = False,
) -> DailyDriverRunResult:
    """Manual recovery job. Missing-only by default; force replaces rows."""
    if not can_proceed():
        return DailyDriverRunResult(
            status="skipped_budget", processed=0, created=0, skipped=0, errors=[]
        )

    since = date.today() - timedelta(days=max(1, min(days, 730)))
    async with async_session() as db:
        stmt = select(Stock)
        if ticker:
            stmt = stmt.where(Stock.ticker == ticker.upper())
        else:
            stmt = stmt.join(Favorite, Favorite.stock_id == Stock.id).distinct()
        stocks = (await db.execute(stmt.limit(max(1, min(limit, 200))))).scalars().all()

    processed = created = skipped = 0
    errors: list[str] = []
    rows: list[DailyPriceDriverResponse] = []
    for stock in stocks:
        async with async_session() as db:
            dates = (
                await db.execute(
                    select(PriceHistory.date)
                    .where(
                        PriceHistory.stock_id == stock.id,
                        PriceHistory.date >= since,
                        PriceHistory.date < date.today(),
                    )
                    .order_by(PriceHistory.date.asc())
                )
            ).scalars().all()
        for trade_date in dates:
            processed += 1
            try:
                async with async_session() as db:
                    result = await ensure_daily_driver(db, stock, trade_date, force=force)
                    if result is None:
                        skipped += 1
                    else:
                        created += 1
                        rows.append(_response(stock.ticker, result))
            except Exception as e:  # noqa: BLE001
                logger.exception("daily driver backfill failed %s %s", stock.ticker, trade_date)
                errors.append(f"{stock.ticker} {trade_date}: {e}")

    return DailyDriverRunResult(
        status="ok",
        processed=processed,
        created=created,
        skipped=skipped,
        errors=errors,
        rows=rows[:20],
    )


async def latest_completed_trade_date(db: AsyncSession, stock_id: int) -> date | None:
    return (
        await db.execute(
            select(func.max(PriceHistory.date)).where(
                PriceHistory.stock_id == stock_id,
                PriceHistory.date < date.today(),
            )
        )
    ).scalar_one_or_none()


async def ensure_daily_driver(
    db: AsyncSession,
    stock: Stock,
    trade_date: date,
    force: bool = False,
) -> DailyPriceDriver | None:
    existing = (
        await db.execute(
            select(DailyPriceDriver).where(
                DailyPriceDriver.stock_id == stock.id,
                DailyPriceDriver.trade_date == trade_date,
                DailyPriceDriver.model_version == MODEL_VERSION,
            )
        )
    ).scalar_one_or_none()
    if existing is not None and not force:
        return None

    evidence = await _collect_evidence(db, stock, trade_date)
    source_hash = _source_hash(evidence)
    if existing is not None and existing.source_hash == source_hash and not force:
        return None
    if existing is not None and force:
        await db.execute(delete(DailyPriceDriver).where(DailyPriceDriver.id == existing.id))
        await db.flush()

    payload = await _llm_extract_driver(stock, trade_date, evidence)
    row = DailyPriceDriver(
        stock_id=stock.id,
        trade_date=trade_date,
        direction=payload.get("direction") or "neutral",
        keywords=payload.get("keywords") or ["원인 미확인"],
        summary=payload.get("summary") or "확인된 직접 원인이 부족합니다.",
        evidence=evidence,
        confidence=payload.get("confidence"),
        source_hash=source_hash,
        model_version=MODEL_VERSION,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _collect_evidence(db: AsyncSession, stock: Stock, trade_date: date) -> dict[str, Any]:
    price = (
        await db.execute(
            select(PriceHistory)
            .where(PriceHistory.stock_id == stock.id, PriceHistory.date == trade_date)
        )
    ).scalar_one_or_none()
    prev_price = (
        await db.execute(
            select(PriceHistory)
            .where(PriceHistory.stock_id == stock.id, PriceHistory.date < trade_date)
            .order_by(PriceHistory.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    news_rows = (
        await db.execute(
            select(News)
            .where(News.stock_id == stock.id, func.date(News.published_at) == trade_date)
            .order_by(News.published_at.desc())
            .limit(_NEWS_LIMIT)
        )
    ).scalars().all()
    analysis = (
        await db.execute(
            select(Analysis)
            .where(
                Analysis.stock_id == stock.id,
                Analysis.schema_version == "v2",
                Analysis.date == trade_date,
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    day_change_pct = None
    if price is not None and prev_price is not None and prev_price.close:
        day_change_pct = round((price.close - prev_price.close) / prev_price.close * 100, 2)

    card = analysis.card_data if analysis and isinstance(analysis.card_data, dict) else {}
    return {
        "stock": {"ticker": stock.ticker, "name": stock.name, "market": stock.market},
        "trade_date": trade_date.isoformat(),
        "price": {
            "open": getattr(price, "open", None),
            "high": getattr(price, "high", None),
            "low": getattr(price, "low", None),
            "close": getattr(price, "close", None),
            "volume": getattr(price, "volume", None),
            "day_change_pct": day_change_pct,
        },
        "card": {
            "glance": card.get("glance"),
            "recent_price_move": card.get("recent_price_move"),
            "thesis_catalysts": (card.get("thesis") or {}).get("catalysts"),
            "relations_one_line": (card.get("relations") or {}).get("one_line"),
        },
        "news": [
            {
                "id": n.id,
                "title": n.title,
                "source": n.source,
                "url": n.url,
                "published_at": n.published_at.isoformat() if n.published_at else None,
                "content": (n.content or "")[:_BODY_LIMIT],
            }
            for n in news_rows
        ],
    }


async def _llm_extract_driver(stock: Stock, trade_date: date, evidence: dict[str, Any]) -> dict:
    prompt = f"""역할: 주식 데일리 가격 원인 편집자.

목표: 이미 끝난 거래일 {trade_date.isoformat()} 하루의 상승/하락 원인을 투자자가 차트에서 볼 수 있는 "종합 키워드"로 확정한다.

중요:
- 뉴스 제목을 그대로 복사하지 마라.
- 여러 뉴스/공시/가격/관계/분석 내용을 합쳐 원인 키워드를 만든다.
- 키워드는 명사형 2~12자 내외가 아니라, 투자자가 바로 이해하는 짧은 구절이어야 한다.
  좋은 예: "OpenAI 계약 기대", "노조 파업 리스크", "Azure AI 수요 확대", "실적 전망 하향", "외국인 매도 전환"
- 하루가 끝난 뒤의 과거 데이터다. 확정된 기록으로 저장될 것이므로 과장하지 마라.
- 근거가 부족하면 "원인 미확인"을 포함하고 confidence="low"로 둔다.
- 한국어로만 출력한다.

증거 JSON:
{json.dumps(evidence, ensure_ascii=False, default=str)[:14000]}

응답 JSON 1개:
{{
  "direction": "positive | negative | mixed | neutral",
  "keywords": ["종합 원인 키워드 1", "종합 원인 키워드 2"],
  "summary": "그날 주가 움직임을 설명하는 한 문장",
  "confidence": "high | medium | low"
}}
"""
    raw = await get_analyst_adapter().generate_json(prompt)
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, dict):
        return {}
    keywords = parsed.get("keywords")
    if not isinstance(keywords, list):
        parsed["keywords"] = ["원인 미확인"]
    else:
        parsed["keywords"] = [str(k).strip()[:40] for k in keywords if str(k).strip()][:5]
    if parsed.get("direction") not in {"positive", "negative", "mixed", "neutral"}:
        parsed["direction"] = _direction_from_price(evidence)
    if parsed.get("confidence") not in {"high", "medium", "low"}:
        parsed["confidence"] = "medium"
    return parsed


def _direction_from_price(evidence: dict[str, Any]) -> str:
    pct = ((evidence.get("price") or {}).get("day_change_pct"))
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _source_hash(evidence: dict[str, Any]) -> str:
    source = {
        "trade_date": evidence.get("trade_date"),
        "price": evidence.get("price"),
        "news_ids": [n.get("id") for n in evidence.get("news", [])],
        "news_titles": [n.get("title") for n in evidence.get("news", [])],
        "card": evidence.get("card"),
    }
    return hashlib.sha256(
        json.dumps(source, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _response(ticker: str, row: DailyPriceDriver) -> DailyPriceDriverResponse:
    return DailyPriceDriverResponse(
        id=row.id,
        ticker=ticker,
        trade_date=row.trade_date,
        direction=row.direction,  # type: ignore[arg-type]
        keywords=[str(k) for k in row.keywords],
        summary=row.summary,
        evidence=row.evidence,
        confidence=row.confidence,
        model_version=row.model_version,
        created_at=row.created_at,
    )
