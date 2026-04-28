"""Pure-Python technical indicators. Deterministic. Returns None when data insufficient."""
from __future__ import annotations


def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i, _ in enumerate(values):
        if i + 1 < period:
            out.append(None)
        else:
            out.append(sum(values[i - period + 1 : i + 1]) / period)
    return out


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI. Returns latest value."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def atr_pct(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    """ATR as percentage of latest close. True Range = max(H-L, |H-prevC|, |L-prevC|)."""
    if len(closes) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return (atr / closes[-1]) * 100.0


def ma_stack(closes: list[float]) -> str | None:
    """정배열 if MA5 > MA20 > MA60, 역배열 if reversed, else 혼조."""
    if len(closes) < 60:
        return None
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    if ma5 > ma20 > ma60:
        return "정배열"
    if ma5 < ma20 < ma60:
        return "역배열"
    return "혼조"


def rvol(volumes: list[float], period: int = 20) -> float | None:
    """Latest volume / mean(volumes[-period:])."""
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-period - 1 : -1]) / period
    if avg == 0:
        return None
    return volumes[-1] / avg


def obv_ratio(closes: list[float], volumes: list[float], period: int = 20) -> float | None:
    """OBV change over `period` / total volume in `period`. Bounded ~[-1, 1]."""
    if len(closes) < period + 1 or len(volumes) < period + 1:
        return None
    obv = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv += volumes[i]
        elif closes[i] < closes[i - 1]:
            obv -= volumes[i]
    total_vol = sum(volumes[-period:])
    if total_vol == 0:
        return None
    return obv / total_vol


def cmf(
    highs: list[float], lows: list[float], closes: list[float], volumes: list[float], period: int = 20
) -> float | None:
    """Chaikin Money Flow over `period`. In [-1, 1]."""
    if len(closes) < period:
        return None
    mf_volumes = []
    for i in range(-period, 0):
        h, l, c = highs[i], lows[i], closes[i]
        if h == l:
            mf_volumes.append(0.0)
            continue
        mf_mult = ((c - l) - (h - c)) / (h - l)
        mf_volumes.append(mf_mult * volumes[i])
    total_vol = sum(volumes[-period:])
    if total_vol == 0:
        return None
    return sum(mf_volumes) / total_vol
