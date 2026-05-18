"""최근 가격 움직임 분석 — "왜 떨어졌나/올랐나" 답 layer.

사용자 피드백 (2026-05-19): "한미반도체가 며칠 떨어지는데 카드 봤을 때
왜 떨어지는지 안 보임". 시니어 펀더멘털 분석가가 본 한 줄 + 원인 1-3개.

흐름:
  1. PriceHistory 에서 5/14/30 거래일 수익률 계산 (deterministic)
  2. 그 기간 News / 공시(Disclosure) / political_signal / KR flow 매칭
  3. LLM 에 raw 던져 narrative 생성. 증거 부족 시 unknown_or_unconfirmed 명시.

Beyond Meat 류 환상 재발 방지 가드:
  - "본문에 없는 사실 생성 금지" prompt-level
  - 후보 evidence (date + summary) 만 입력 — LLM 이 *조합/요약* 만 함
  - confidence 'low' 도 허용 (밸류 부담 같은 추정 가능)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.database import async_session
from app.models import Disclosure, News, PriceHistory, Stock
from app.models.political_signal import PoliticalSignal, PoliticalSignalTicker
from app.schemas.card import PriceMoveCause, RecentPriceMove

logger = logging.getLogger(__name__)

_WINDOWS = (5, 14, 30)
_BIG_MOVE_THRESHOLD = 3.0  # 단일일 ±3%+ 면 "급변동" 라벨
_MAX_EVENTS = 12  # LLM 입력 토큰 제한
_MAX_CAUSES = 3


async def fetch_recent_price_move(ticker: str) -> RecentPriceMove | None:
    """전체 흐름. 가격 데이터 부족 시 None."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return None

        # 1) 최근 30 거래일 가격 데이터
        rows = (
            await db.execute(
                select(PriceHistory)
                .where(PriceHistory.stock_id == stock.id)
                .order_by(PriceHistory.date.desc())
                .limit(40)
            )
        ).scalars().all()
        if len(rows) < 2:
            return None

        # 시간 순 (오래된 → 최근) 정렬
        rows = list(reversed(rows))
        return_data = _compute_returns(rows)
        if return_data is None:
            return None

        # 2) 그 기간 evidence 후보
        primary_days = {"5d": 5, "14d": 14, "30d": 30}[return_data["primary_window"]]
        since = datetime.utcnow() - timedelta(days=primary_days + 1)
        events = await _gather_events(db, stock, since)

    # 3) LLM narrative — 별도 mini call. 호출 실패 시 fallback deterministic 한 줄.
    narrative_data = await _llm_narrate(stock, return_data, events)

    one_line = narrative_data.get("one_line") or _fallback_one_line(return_data)
    causes_raw = narrative_data.get("causes") or []
    unknown = narrative_data.get("unknown_or_unconfirmed")

    causes: list[PriceMoveCause] = []
    for c in causes_raw[:_MAX_CAUSES]:
        try:
            causes.append(PriceMoveCause.model_validate(c))
        except Exception as e:  # noqa: BLE001
            logger.info("recent_price_move drop invalid cause: %s — %s", c, e)

    return RecentPriceMove(
        return_5d_pct=return_data.get("5d"),
        return_14d_pct=return_data.get("14d"),
        return_30d_pct=return_data.get("30d"),
        primary_window=return_data["primary_window"],
        biggest_move_date=return_data.get("biggest_move_date"),
        biggest_move_pct=return_data.get("biggest_move_pct"),
        one_line=one_line,
        causes=causes,
        unknown_or_unconfirmed=unknown,
    )


def _compute_returns(rows: list[PriceHistory]) -> dict[str, Any] | None:
    """5/14/30 거래일 수익률 + 대표 윈도우 + 단일일 최대 변동."""
    if len(rows) < 2:
        return None
    latest = rows[-1]
    if latest.close <= 0:
        return None

    result: dict[str, Any] = {}
    biggest_pct = 0.0
    biggest_date = None
    for i in range(len(rows) - 1):
        prev_close = rows[i].close
        next_close = rows[i + 1].close
        if prev_close <= 0:
            continue
        day_pct = (next_close - prev_close) / prev_close * 100
        if abs(day_pct) > abs(biggest_pct):
            biggest_pct = day_pct
            biggest_date = (
                rows[i + 1].date.isoformat()
                if hasattr(rows[i + 1].date, "isoformat")
                else str(rows[i + 1].date)
            )

    for window in _WINDOWS:
        if len(rows) <= window:
            continue
        base = rows[-(window + 1)]
        if base.close <= 0:
            continue
        result[f"{window}d"] = round(
            (latest.close - base.close) / base.close * 100, 2
        )

    if not result:
        return None
    # 대표 윈도우 — 가장 큰 절대 변동.
    primary = max(result, key=lambda k: abs(result[k]))
    result["primary_window"] = primary

    if biggest_date and abs(biggest_pct) >= _BIG_MOVE_THRESHOLD:
        result["biggest_move_date"] = biggest_date
        result["biggest_move_pct"] = round(biggest_pct, 2)

    return result


async def _gather_events(db, stock: Stock, since: datetime) -> list[dict]:
    """News + 공시 + political_signal + flow 를 날짜 매칭으로 후보 list 생성.
    LLM 입력용 raw — 시간 순 정렬, 가장 최근 _MAX_EVENTS 만."""
    events: list[dict] = []

    # News
    news_rows = (
        await db.execute(
            select(News)
            .where(News.stock_id == stock.id, News.published_at >= since)
            .order_by(News.published_at.desc())
            .limit(_MAX_EVENTS)
        )
    ).scalars().all()
    for n in news_rows:
        events.append({
            "kind": "news",
            "date": n.published_at.isoformat() if n.published_at else None,
            "summary": (n.title or "")[:200],
            "body_snippet": ((n.content or "")[:300]) if n.content else None,
        })

    # 공시 (Disclosure)
    try:
        disc_rows = (
            await db.execute(
                select(Disclosure)
                .where(
                    Disclosure.stock_id == stock.id,
                    Disclosure.disclosed_at >= since,
                )
                .order_by(Disclosure.disclosed_at.desc())
                .limit(_MAX_EVENTS // 2)
            )
        ).scalars().all()
        for d in disc_rows:
            events.append({
                "kind": "disclosure",
                "date": d.disclosed_at.isoformat() if d.disclosed_at else None,
                "summary": (d.title or "")[:200],
            })
    except Exception as e:  # noqa: BLE001
        # 공시 모델 컬럼 다를 수 있음 — 무시.
        logger.info("price_move disclosure skip: %s", e)

    # Political signal (트럼프 truth 등) — 이 ticker 매핑된 것만.
    pol_rows = (
        await db.execute(
            select(PoliticalSignal, PoliticalSignalTicker)
            .join(
                PoliticalSignalTicker,
                PoliticalSignalTicker.signal_id == PoliticalSignal.id,
            )
            .where(
                PoliticalSignalTicker.ticker == stock.ticker,
                PoliticalSignal.posted_at >= since,
            )
            .order_by(PoliticalSignal.posted_at.desc())
            .limit(5)
        )
    ).all()
    for sig, _impact in pol_rows:
        events.append({
            "kind": "political",
            "date": sig.posted_at.isoformat() if sig.posted_at else None,
            "summary": (sig.summary_ko or "")[:200],
        })

    # 가장 최근 _MAX_EVENTS 까지만.
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return events[:_MAX_EVENTS]


async def _llm_narrate(
    stock: Stock, return_data: dict, events: list[dict]
) -> dict[str, Any]:
    """별도 mini LLM call — narrative 1 줄 + causes 1-3개. 실패 시 빈 dict."""
    primary = return_data["primary_window"]
    primary_pct = return_data.get(primary)

    events_block = "\n".join(
        f"- [{e['kind']}] {e.get('date', '?')[:10]}: {e['summary']}"
        + (f"\n  본문: {e['body_snippet']}" if e.get("body_snippet") else "")
        for e in events
    ) or "(이 기간 News / 공시 / political signal 0건)"

    biggest_line = (
        f"단일일 최대 변동: {return_data['biggest_move_pct']:+.2f}% ({return_data['biggest_move_date']})"
        if return_data.get("biggest_move_date")
        else "단일일 큰 변동 없음 (천천히 변화)"
    )

    prompt = f"""역할: 30년 경력 펀더멘털 분석가. {stock.ticker}({stock.name or stock.ticker}) 의 최근 가격 움직임을 *왜* 한 줄로 설명한다. 자료에 없으면 절대 추측 X — unknown_or_unconfirmed 에 명시.

가격 변화:
- 5거래일: {return_data.get('5d', '?')}%
- 14거래일: {return_data.get('14d', '?')}%
- 30거래일: {return_data.get('30d', '?')}%
- 대표 윈도우: {primary} ({primary_pct}%)
- {biggest_line}

이 기간 raw 자료 (News / 공시 / political):
{events_block}

응답 JSON 1개:
{{
  "one_line": "최근 {primary} -X% — [한 줄 원인 요약, 가족 비전공자 친화]",
  "causes": [
    {{
      "text": "한 줄 원인 (예: 'HBM 경쟁 격화로 매출 의존도 우려')",
      "confidence": "high | medium | low",
      "evidence_kind": "news | disclosure | political | flow | valuation | peer_move",
      "evidence_date": "YYYY-MM-DD 또는 null",
      "evidence_quote": "위 raw 본문에서 그대로 인용한 1 줄 (paraphrase 금지) 또는 null"
    }}
  ],
  "unknown_or_unconfirmed": "확인된 직접 원인 부족 시 한 줄 (예: '단기 수급/밸류에이션 조정으로 추정 — 명시 catalyst 없음') 또는 null"
}}

엄격 규칙:
1. raw 자료에 없는 사실 생성 X. evidence_kind 가 valuation/peer_move 면 evidence_date/quote 는 null OK.
2. causes 1-3 개. 확실하지 않으면 unknown_or_unconfirmed 만 적고 causes 비움.
3. confidence='high' 는 evidence_quote 본문 인용 + 명시 사실일 때만.
4. one_line 가족 비전공자 친화 — "HBM 경쟁 격화" 같이 짧고 명확. 약어 X.
5. JSON 1 개. 자연어 / 코드펜스 X.
"""

    try:
        from app.services.llm.adapter import get_adapter

        raw = await get_adapter().generate_json(prompt)
    except Exception as e:  # noqa: BLE001
        logger.warning("price_move LLM failed for %s: %s", stock.ticker, e)
        return {}

    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as e:
        logger.warning("price_move JSON parse failed for %s: %s", stock.ticker, e)
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _fallback_one_line(return_data: dict) -> str:
    """LLM 실패 시 deterministic 한 줄."""
    primary = return_data["primary_window"]
    pct = return_data.get(primary, 0)
    label = {"5d": "5거래일", "14d": "14거래일", "30d": "30거래일"}[primary]
    direction = "하락" if pct < 0 else "상승" if pct > 0 else "변동 없음"
    return f"최근 {label} {pct:+.1f}% — {direction}"
