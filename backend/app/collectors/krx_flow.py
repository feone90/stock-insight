"""pykrx — KR 종목 수급(외국인/기관 5일 순매수).

Codex 시니어 트레이더 리뷰(2026-05-14): KR retail 의 매매 판단은
외국인/기관 수급(market sponsorship)을 빼면 빈 카드. yfinance 도 dartlab 도
이 영역은 제공하지 않는다. pykrx 의 KRX 공식 일별 데이터로 보강.

2026-05-14 사용자 결정: 공매도 잔고/회전은 가족 비전공자 retail 의사결정에
nuanced + noise > signal 이라 drop. 외국인/기관 수급만 살림.

ad-hoc 호출 패턴 — 카드 분석 시점에 직접 fetch. 별도 DB 테이블/스케줄러
없이 카드 cache(5분)가 사실상 캐시 역할. 가족 dev 트래픽 기준 충분.

Returns dict 형식 (collector pattern, 예외 던지지 않음):
    {
        "foreign_net_5d_krw": int|None,        # 외국인 5거래일 순매수 (원)
        "inst_net_5d_krw": int|None,           # 기관 5거래일 순매수 (원)
        "foreign_streak_days": int,            # +N 매수 연속 / -N 매도 연속
        "inst_streak_days": int,
        "as_of": str|None,                     # 최근 거래일 (YYYY-MM-DD)
        "error": str | absent,
    }
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _streak_days(values: list[float]) -> int:
    """가장 최근 row 부터 부호가 유지된 연속 일수.

    +N → 최근 N일 연속 순매수 / -N → 연속 순매도 / 0 → 부호 0 또는 데이터 없음.
    """
    if not values:
        return 0
    last = values[-1]
    if last == 0:
        return 0
    sign = 1 if last > 0 else -1
    count = 0
    for v in reversed(values):
        if v == 0:
            break
        if (v > 0 and sign > 0) or (v < 0 and sign < 0):
            count += 1
        else:
            break
    return count * sign


_FLOW_COL_CANDIDATES = [
    (["외국인합계", "외국인"], "foreign_net_5d_krw", "foreign_streak_days"),
    (["기관합계", "기관"], "inst_net_5d_krw", "inst_streak_days"),
]


def _parse_flow_df(df, out: dict) -> None:
    """flow DataFrame → out dict 필드 채움. pykrx 컬럼명이 버전마다 흔들림."""
    if df is None or df.empty:
        return
    recent5 = df.tail(5)
    for col_candidates, total_key, streak_key in _FLOW_COL_CANDIDATES:
        col = next((c for c in col_candidates if c in df.columns), None)
        if col is None:
            continue
        try:
            out[total_key] = int(recent5[col].sum())
            out[streak_key] = _streak_days([float(v) for v in df[col].tolist()])
        except Exception as e:  # noqa: BLE001
            logger.warning("pykrx flow col %s parse fail: %s", col, e)
    try:
        last_idx = df.index[-1]
        out["as_of"] = (
            last_idx.date().isoformat() if hasattr(last_idx, "date") else None
        )
    except Exception:  # noqa: BLE001
        pass


def fetch_kr_flow(ticker: str) -> dict:  # pragma: no cover
    """pykrx 로 한 종목 수급 스냅샷 조회.

    pykrx 가 KRX 사이트 scraping 이라 실패 가능. graceful — 부분 결과만 반환.
    카드 입장에서 "이 필드 없으면 섹션 숨김" 패턴이 자연스럽다.
    """
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        return {"error": "pykrx 미설치"}

    today = date.today()
    flow_start = today - timedelta(days=21)   # 5거래일 + 주말/공휴일 흡수

    out: dict = {
        "foreign_net_5d_krw": None,
        "inst_net_5d_krw": None,
        "foreign_streak_days": 0,
        "inst_streak_days": 0,
        "as_of": None,
    }

    try:
        flow_df = pykrx_stock.get_market_trading_value_by_date(
            _ymd(flow_start), _ymd(today), ticker
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("pykrx flow fetch failed for %s: %s", ticker, e)
        flow_df = None
    _parse_flow_df(flow_df, out)

    return out
