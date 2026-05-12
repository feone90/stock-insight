"""LLM analyzer — 정치 발언 → 영향 종목 매핑 (strict structured output).

미래 자동매매 trigger schema. Pydantic v2 strict validation으로 LLM
hallucination 방어 + universe 후처리 filter.

Pipeline:
  1. Tier 1+2 universe ticker hint를 prompt에 일부 첨부
  2. LLM 호출 → strict JSON
  3. Pydantic validate
  4. universe 후처리 filter (LLM이 만든 ticker 중 우리 DB에 없는 거 drop)
  5. political_signals (cache) + political_signal_tickers (1:N) upsert
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.political_signal import PoliticalSignal, PoliticalSignalTicker
from app.models.stock import Stock
from app.services.analyst import get_analyst_adapter

logger = logging.getLogger(__name__)

ANALYZER_VERSION = "political_v1"
MAX_HINT_TICKERS_PER_MARKET = 40  # prompt size 보호


class TickerImpact(BaseModel):
    """단일 종목에 미치는 영향 — 자동매매 trigger 단위."""

    ticker: str = Field(
        description="KR 6자리 숫자 (예 005930) 또는 US 1~5자 알파벳 (예 AAPL). universe 안에 있는 것만."
    )
    sentiment: Literal["bullish", "bearish", "neutral"]
    direction: Literal["long", "short", "avoid"] = Field(
        description="자동매매 action: long=매수, short=매도/공매도, avoid=관망"
    )
    strength: Literal["high", "medium", "low"]
    confidence: float = Field(
        ge=0, le=1, description="LLM 자체 confidence (0~1). 추측은 0.5 미만."
    )
    expected_window: Literal["minutes", "hours", "1-3days", "1-2weeks"]
    reasoning: str = Field(description="왜 이 종목에 영향? 한국어 1~3문장.")
    sector_impact: str | None = Field(default=None)


class TruthSocialAnalysis(BaseModel):
    """발언 단위 분석 결과 — political_signals row update + impacts 1:N."""

    is_market_relevant: bool = Field(
        description="시장에 의미 있는 발언인가. 스포츠/개인공격/일상은 false."
    )
    summary_ko: str = Field(description="발언 1줄 한국어 요약")
    overall_sentiment: Literal["bullish", "bearish", "neutral", "mixed"]
    macro_themes: list[str] = Field(
        default_factory=list,
        description='"관세", "지정학", "금리", "AI/반도체", "에너지", "이민" 등',
    )
    impacts: list[TickerImpact] = Field(default_factory=list)


PROMPT_TEMPLATE = """너는 정치-주식 영향 분석 전문가다. 트럼프(@realDonaldTrump)의 Truth Social 발언이 한국/미국 주식 시장에 미치는 영향을 분석해 STRICT JSON으로만 응답하라. 마크다운/설명/code fence 금지.

## 발언
posted_at: {posted_at}
content: {content}

## Universe hint (이 ticker 중에서만 영향 식별. 다른 ticker 만들지 마라.)
KR 주요 종목: {kr_hint}
US 주요 종목: {us_hint}

## 규칙
1. is_market_relevant=false면 impacts=[] (스포츠/개인공격/사적 발언은 noise)
2. impacts ticker는 위 hint 안에 있는 것만. 모르면 빈 배열.
3. 명백한 인과만. 추측은 confidence < 0.5로 낮춰라.
4. direction은 자동매매 action 매핑:
   - 명확한 호재 + bullish → long
   - 명확한 악재 + bearish → short
   - 양방향 또는 불확실 → avoid
5. expected_window: 즉시 반응(minutes/hours) vs 정책 lag(1-2weeks)
6. reasoning: 한국어 1~3문장 (가족 친화)
7. macro_themes 예: "관세", "지정학", "금리", "AI/반도체", "에너지", "이민"

## 예시 패턴
- 중국 관세 인상 → US 반도체(NVDA/AMD) bearish/short, KR 반도체(005930/000660) bearish/avoid
- AI 인프라 발표 → US AI(NVDA/MSFT) bullish/long, KR HBM(000660) bullish/long
- 이란 제재 → 정유주(XOM) bullish, 항공(DAL) bearish

## 출력 (TruthSocialAnalysis JSON)
{{
  "is_market_relevant": bool,
  "summary_ko": "...",
  "overall_sentiment": "bullish"|"bearish"|"neutral"|"mixed",
  "macro_themes": [...],
  "impacts": [
    {{
      "ticker": "...",
      "sentiment": "...",
      "direction": "long"|"short"|"avoid",
      "strength": "high"|"medium"|"low",
      "confidence": 0.0~1.0,
      "expected_window": "...",
      "reasoning": "...",
      "sector_impact": "..."|null
    }}
  ]
}}
"""


async def _universe_hint(db: AsyncSession) -> tuple[list[str], list[str], set[str]]:
    """Tier 1+2 universe — prompt hint용 cap된 list + 전체 set (후처리 filter용)."""
    kr_rows = (
        await db.execute(
            select(Stock.ticker, Stock.name)
            .where(Stock.tier.in_([1, 2]), Stock.market.in_(["KOSPI", "KOSDAQ", "KRX"]))
            .order_by(Stock.tier.asc())
            .limit(MAX_HINT_TICKERS_PER_MARKET)
        )
    ).all()
    us_rows = (
        await db.execute(
            select(Stock.ticker, Stock.name)
            .where(Stock.tier.in_([1, 2]), Stock.market.in_(["NASDAQ", "NYSE", "US", "NMS"]))
            .order_by(Stock.tier.asc())
            .limit(MAX_HINT_TICKERS_PER_MARKET)
        )
    ).all()
    kr_hint = ", ".join(f"{t}({n})" for t, n in kr_rows)
    us_hint = ", ".join(f"{t}({n})" for t, n in us_rows)

    # 전체 universe (후처리 filter용)
    all_rows = (
        await db.execute(
            select(Stock.ticker).where(Stock.tier.in_([1, 2]))
        )
    ).scalars().all()
    all_universe = set(all_rows)
    return kr_hint, us_hint, all_universe


async def analyze_signal(
    signal: PoliticalSignal,
    kr_hint: str,
    us_hint: str,
) -> TruthSocialAnalysis | None:
    """LLM 1회 호출 + Pydantic validate. 실패 시 None 반환."""
    adapter = get_analyst_adapter()
    prompt = PROMPT_TEMPLATE.format(
        posted_at=signal.posted_at.isoformat(),
        content=signal.content[:2000],
        kr_hint=kr_hint or "(empty)",
        us_hint=us_hint or "(empty)",
    )
    raw = ""
    try:
        raw = await adapter.generate_json(prompt)
        logger.info(
            "political analyzer raw len=%d for signal %s", len(raw or ""), signal.id
        )
        data = json.loads(raw)
        return TruthSocialAnalysis.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning(
            "political analyzer parse fail signal %s: %s | raw[:800]: %s",
            signal.id, e, (raw or "")[:800],
        )
        return None
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "political analyzer LLM call fail signal %s: %s | raw[:200]: %s",
            signal.id, e, (raw or "")[:200],
        )
        return None


async def analyze_pending_signals(db: AsyncSession, limit: int = 20) -> dict:
    """analyzed_at IS NULL 인 signal LLM 분석 + upsert. cost guard 외부.

    Returns: {"analyzed": int, "skipped": int, "ticker_rows_inserted": int}
    """
    kr_hint, us_hint, all_universe = await _universe_hint(db)

    pending = (
        await db.execute(
            select(PoliticalSignal)
            .where(PoliticalSignal.analyzed_at.is_(None))
            .order_by(PoliticalSignal.posted_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    if not pending:
        return {"analyzed": 0, "skipped": 0, "ticker_rows_inserted": 0}

    analyzed = 0
    skipped = 0
    inserted_tickers = 0

    for signal in pending:
        result = await analyze_signal(signal, kr_hint, us_hint)
        if result is None:
            skipped += 1
            continue

        signal.analyzed_at = datetime.utcnow()
        signal.is_market_relevant = result.is_market_relevant
        signal.summary_ko = result.summary_ko
        signal.overall_sentiment = result.overall_sentiment
        signal.macro_themes = result.macro_themes
        signal.analyzer_version = ANALYZER_VERSION

        if result.is_market_relevant:
            for impact in result.impacts:
                t = impact.ticker.strip().upper()
                # universe 후처리 filter — LLM hallucination 방어
                if t not in all_universe:
                    continue
                stmt = (
                    pg_insert(PoliticalSignalTicker)
                    .values(
                        signal_id=signal.id,
                        ticker=t,
                        sentiment=impact.sentiment,
                        direction=impact.direction,
                        strength=impact.strength,
                        confidence=impact.confidence,
                        expected_window=impact.expected_window,
                        reasoning=impact.reasoning,
                        sector_impact=impact.sector_impact,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_political_signal_ticker",
                    )
                )
                r = await db.execute(stmt)
                if r.rowcount and r.rowcount > 0:
                    inserted_tickers += 1
        analyzed += 1

    await db.commit()
    logger.info(
        "political analyzer: analyzed=%d skipped=%d ticker_rows=%d",
        analyzed,
        skipped,
        inserted_tickers,
    )
    return {
        "analyzed": analyzed,
        "skipped": skipped,
        "ticker_rows_inserted": inserted_tickers,
    }
