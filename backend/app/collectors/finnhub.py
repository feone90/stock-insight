"""Finnhub free tier — US earnings calendar + analyst recommendation consensus.

Codex 시니어 트레이더 리뷰(2026-05-14) priority 4 — earnings 시점과 analyst
sentiment 가 US 매매 결정 context 의 일부. 이전엔 우리 카드에 둘 다 없었음.

API:
- `/calendar/earnings?from=YYYY-MM-DD&to=YYYY-MM-DD&symbol=AAPL` — earnings 이벤트
- `/stock/recommendation?symbol=AAPL` — 매수/보유/매도 의견 분포 월별 시계열

키 없으면 graceful skip (collector pattern). 60 req/min 제한이라 ticker per
card 기준 충분. 키 발급: https://finnhub.io/dashboard.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 15.0


async def fetch_earnings_calendar(ticker: str, days_ahead: int = 90) -> dict | None:
    """다음 실적 발표 1건만. 카드엔 'D-N' 형식으로 노출.

    days_ahead 윈도우 안에 발표 없으면 None. 발표는 quarter 1번씩이라
    90일이면 거의 모든 종목 포함.

    Returns: {"date": "YYYY-MM-DD", "eps_estimate": float|None,
              "revenue_estimate": int|None, "hour": "bmo"|"amc"|"dmh"}
    """
    if not settings.finnhub_api_key:
        return None

    today = date.today()
    end = today + timedelta(days=days_ahead)
    params = {
        "from": today.isoformat(),
        "to": end.isoformat(),
        "symbol": ticker.upper(),
        "token": settings.finnhub_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/calendar/earnings", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("finnhub earnings fetch failed for %s: %s", ticker, e)
        return None

    items = data.get("earningsCalendar") or []
    if not items:
        return None
    items.sort(key=lambda x: x.get("date", ""))
    e = items[0]
    return {
        "date": e.get("date"),
        "eps_estimate": e.get("epsEstimate"),
        "revenue_estimate": e.get("revenueEstimate"),
        # bmo = before market open, amc = after market close, dmh = during.
        "hour": e.get("hour"),
    }


async def fetch_price_target(ticker: str) -> dict | None:
    """분석가 1년 목표주가 consensus (high/low/mean/median + analyst count).

    Codex review 후속 — 사용자 명시(2026-05-14): "각 기관들이 정한 목표주가도
    표시되면 좋을것같고". analyst recommendation 옆에 같이 노출.

    Returns: {"target_high", "target_low", "target_mean", "target_median",
              "n_analysts", "last_updated"} (YYYY-MM-DD) 또는 None.
    """
    if not settings.finnhub_api_key:
        return None

    params = {"symbol": ticker.upper(), "token": settings.finnhub_api_key}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/stock/price-target", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("finnhub price target fetch failed for %s: %s", ticker, e)
        return None

    if not isinstance(data, dict) or not data.get("targetMean"):
        return None
    return {
        "target_high": float(data.get("targetHigh") or 0) or None,
        "target_low": float(data.get("targetLow") or 0) or None,
        "target_mean": float(data.get("targetMean") or 0) or None,
        "target_median": float(data.get("targetMedian") or 0) or None,
        "n_analysts": int(data.get("numberOfAnalysts") or 0) or None,
        "last_updated": data.get("lastUpdated"),
    }


async def fetch_analyst_recommendation(ticker: str) -> dict | None:
    """가장 최근 월의 analyst 의견 분포.

    Returns: {"month": "YYYY-MM", "buy": int, "hold": int, "sell": int,
              "strong_buy": int, "strong_sell": int}
    """
    if not settings.finnhub_api_key:
        return None

    params = {"symbol": ticker.upper(), "token": settings.finnhub_api_key}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/stock/recommendation", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "finnhub recommendation fetch failed for %s: %s", ticker, e
        )
        return None

    if not isinstance(data, list) or not data:
        return None
    # 가장 최신 row 가 첫 번째일 수도, 마지막일 수도 있음 — period(YYYY-MM-DD) 기준.
    latest = max(data, key=lambda x: x.get("period", ""))
    return {
        "month": (latest.get("period") or "")[:7],  # YYYY-MM
        "buy": int(latest.get("buy") or 0),
        "hold": int(latest.get("hold") or 0),
        "sell": int(latest.get("sell") or 0),
        "strong_buy": int(latest.get("strongBuy") or 0),
        "strong_sell": int(latest.get("strongSell") or 0),
    }
