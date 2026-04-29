"""get_adapter_for() router — KR/US dispatch + singleton (3 cases)."""
import pytest

from app.services.external_data_adapters import (
    DartlabAdapter,
    SecEdgarAdapter,
    get_adapter_for,
)


def test_kr_six_digit_ticker_routes_to_dartlab():
    assert isinstance(get_adapter_for("005930"), DartlabAdapter)


def test_us_alpha_ticker_routes_to_sec_edgar():
    assert isinstance(get_adapter_for("AAPL"), SecEdgarAdapter)


def test_router_returns_same_instance_per_market():
    a1 = get_adapter_for("AAPL")
    a2 = get_adapter_for("TSLA")
    assert a1 is a2  # SecEdgarAdapter shared across US tickers (avoids reinit)

    k1 = get_adapter_for("005930")
    k2 = get_adapter_for("000660")
    assert k1 is k2  # DartlabAdapter shared across KR tickers
