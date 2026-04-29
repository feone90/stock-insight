"""AAPL smoke — real SEC EDGAR API. Opt-in via APPLE_SMOKE env.

Avoids hammering SEC during routine test runs. Verifies the SecEdgarAdapter
end-to-end against live data: 5y+ FY series, sector matches GICS Information
Technology, fiscal year-end is late September.

Spec §11 + §15 acceptance #13.
"""
import os

import pytest

from app.services.external_data_adapters import ResultCache, SecEdgarAdapter

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("APPLE_SMOKE"),
        reason="set APPLE_SMOKE=1 to opt in",
    ),
    pytest.mark.skipif(
        not os.environ.get("SEC_USER_AGENT"),
        reason="SEC_USER_AGENT env required (see .env.example)",
    ),
]


@pytest.mark.asyncio
async def test_aapl_real_sec_edgar_returns_5y_series_sector_and_fiscal_year_end():
    adapter = SecEdgarAdapter(cache=ResultCache())

    series = await adapter.fetch_financial_series("AAPL")
    assert series.source == "sec_edgar"
    assert series.ticker == "AAPL"
    assert len(series.rows) >= 5, f"expected ≥5y FY rows, got {len(series.rows)}"
    assert all("period" in r for r in series.rows)

    sector = await adapter.fetch_sector("AAPL")
    assert sector.sector == "Information Technology"
    assert sector.confidence == 0.7  # SIC_MAPPING_HIT_CONFIDENCE
    assert sector.source == "sec_edgar_sic"

    # AAPL fiscal year-end is late September (SEC reports "0928" / "0930")
    fye = await adapter.fetch_fiscal_year_end("AAPL")
    assert fye is not None
    assert fye.startswith("09-"), f"AAPL fiscal year-end should be Sept, got {fye!r}"
