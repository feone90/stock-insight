"""Ticker normalize — spec §7 8 cases."""
import pytest

from app.services.external_data_adapters.ticker import normalize_ticker


def test_kr_clean_six_digit():
    assert normalize_ticker("005930") == ("005930", "KR")


def test_kr_yahoo_ks_suffix_stripped():
    assert normalize_ticker("005930.KS") == ("005930", "KR")


def test_kr_yahoo_kq_suffix_stripped():
    assert normalize_ticker("005930.KQ") == ("005930", "KR")


def test_kr_krx_prefix_stripped():
    assert normalize_ticker("KRX:005930") == ("005930", "KR")


def test_us_uppercase_passthrough():
    assert normalize_ticker("TSLA") == ("TSLA", "US")


def test_us_lowercase_uppercased():
    assert normalize_ticker("tsla") == ("TSLA", "US")


def test_garbage_raises_value_error():
    with pytest.raises(ValueError):
        normalize_ticker("hello world")


def test_empty_raises_value_error():
    with pytest.raises(ValueError):
        normalize_ticker("")
