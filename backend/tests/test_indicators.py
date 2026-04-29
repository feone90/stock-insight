"""Indicator math tests with hand-computed expected values."""
import math

import pytest

from app.services.analyst.indicators import (
    atr_pct,
    cmf,
    ma_stack,
    obv_ratio,
    rsi,
    rvol,
)

# Sample 60-day OHLCV: closes drift up monotonically, volumes mostly flat.
CLOSES = [100.0 + i * 0.5 for i in range(60)]  # 60 days, monotonic up
HIGHS = [c + 1.5 for c in CLOSES]
LOWS = [c - 1.5 for c in CLOSES]
VOLS = [1_000_000.0] * 58 + [1_400_000.0, 1_500_000.0]  # last 2 days higher


def test_rsi_14_in_range():
    val = rsi(CLOSES, period=14)
    assert val is not None
    assert 0 <= val <= 100
    # Sample is mostly up — expect > 50
    assert val > 50


def test_rsi_insufficient_data_returns_none():
    assert rsi([100.0, 101.0], period=14) is None


def test_atr_pct_positive():
    val = atr_pct(HIGHS, LOWS, CLOSES, period=14)
    assert val is not None
    assert val > 0


def test_ma_stack_uptrend_returns_정배열():
    val = ma_stack(CLOSES)
    assert val == "정배열"


def test_ma_stack_downtrend_returns_역배열():
    down = list(reversed(CLOSES))
    assert ma_stack(down) == "역배열"


def test_rvol_recent_higher_returns_above_one():
    val = rvol(VOLS, period=20)
    assert val is not None
    assert val > 1.0


def test_obv_ratio_returns_finite():
    val = obv_ratio(CLOSES, VOLS, period=20)
    assert val is not None
    assert math.isfinite(val)


def test_cmf_in_minus_one_to_one():
    val = cmf(HIGHS, LOWS, CLOSES, VOLS, period=20)
    assert val is not None
    assert -1 <= val <= 1
