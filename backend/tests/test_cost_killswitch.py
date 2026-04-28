"""Cost kill switch tests."""
from app.services.analyst.cost import (
    DailyBudget,
    can_proceed,
    current_spend_usd,
    record_cost,
    reset_today,
)


def test_initial_budget_allows():
    reset_today()
    assert can_proceed() is True
    assert current_spend_usd() == 0.0


def test_record_below_cap_allows(monkeypatch):
    reset_today()
    monkeypatch.setattr(DailyBudget, "cap_usd", 10.0)
    record_cost(0.5)
    record_cost(0.3)
    assert can_proceed() is True


def test_record_at_or_above_cap_blocks(monkeypatch):
    reset_today()
    monkeypatch.setattr(DailyBudget, "cap_usd", 1.0)
    record_cost(0.6)
    record_cost(0.5)
    assert can_proceed() is False


def test_negative_cost_treated_as_zero(monkeypatch):
    reset_today()
    monkeypatch.setattr(DailyBudget, "cap_usd", 1.0)
    record_cost(-5.0)
    assert current_spend_usd() == 0.0
    assert can_proceed() is True
