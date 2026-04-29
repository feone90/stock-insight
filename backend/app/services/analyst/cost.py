"""Per-day cost tracker. In-memory (sufficient for personal scope).

For multi-process deployment, swap to Redis or DB-backed counter. The kill
switch is consulted by the scheduler before each analysis dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date

from app.config import settings


@dataclass
class _State:
    day: _date | None = None
    cost_usd: float = 0.0


_state = _State()


class DailyBudget:
    """Settings indirection so tests can monkeypatch."""

    cap_usd: float = settings.analysis_daily_budget_usd


def reset_today() -> None:
    """Force reset of the in-memory counter to today, zero cost."""
    _state.day = _date.today()
    _state.cost_usd = 0.0


def _ensure_today() -> None:
    today = _date.today()
    if _state.day != today:
        _state.day = today
        _state.cost_usd = 0.0


def record_cost(usd: float) -> None:
    """Add a positive cost increment to today's running total."""
    _ensure_today()
    _state.cost_usd += max(usd, 0.0)


def can_proceed() -> bool:
    """True iff today's spend is strictly below the cap."""
    _ensure_today()
    return _state.cost_usd < DailyBudget.cap_usd


def current_spend_usd() -> float:
    _ensure_today()
    return _state.cost_usd
