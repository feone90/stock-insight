"""Property invariants — spec §12 (2 property cases).

Held across diverse inputs and across schema versions.
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.services.external_data_adapters.base import (
    FinancialSeries,
    IdentityFacts,
)
from app.services.external_data_adapters.ticker import normalize_ticker


@pytest.mark.parametrize(
    "raw",
    [
        "005930",
        "005930.KS",
        "005930.KQ",
        "KRX:005930",
        "krx:005930",      # case-insensitive prefix
        " 005930 ",        # whitespace
        "005930.kS",       # mixed-case suffix
    ],
)
def test_normalize_invariant_diverse_kr_inputs_collapse_to_clean_form(raw):
    """Property: every accepted raw form for KR 005930 normalizes to one
    canonical (ticker, market) pair."""
    assert normalize_ticker(raw) == ("005930", "KR")


def test_schema_invariants_required_fields_enforced():
    """Property: required fields on IdentityFacts / FinancialSeries cannot be
    silently omitted. Pydantic must reject — we never want a half-shaped
    record reaching the data_layer."""
    # name omitted
    with pytest.raises(ValidationError):
        IdentityFacts(
            ticker="005930",
            market="KR",
            currency="KRW",
            fetched_at=datetime.now(timezone.utc),
            source="dartlab",
        )
    # rows omitted
    with pytest.raises(ValidationError):
        FinancialSeries(
            ticker="005930",
            period_type="annual",
            source="dartlab",
            fetched_at=datetime.now(timezone.utc),
        )
