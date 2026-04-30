"""US S&P 500 seed — wikipedia HTML parser cases."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.universe.seed_us import (
    US_SP500_SOURCE,
    _parse_sp500_table,
    fetch_us_universe,
)

_FAKE_HTML = """
<html><body>
<table id="constituents">
  <thead>
    <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th><th>HQ</th><th>Date added</th><th>CIK</th><th>Founded</th></tr>
  </thead>
  <tbody>
    <tr><td>AAPL</td><td>Apple Inc.</td><td>Information Technology</td><td>Technology Hardware, Storage and Peripherals</td><td>Cupertino, CA</td><td>1982-11-30</td><td>0000320193</td><td>1976</td></tr>
    <tr><td>MSFT</td><td>Microsoft</td><td>Information Technology</td><td>Systems Software</td><td>Redmond, WA</td><td>1994-06-01</td><td>0000789019</td><td>1975</td></tr>
    <tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td><td>Multi-Sector Holdings</td><td>Omaha, NE</td><td>2010-02-16</td><td>0001067983</td><td>1839</td></tr>
  </tbody>
</table>
</body></html>
"""


def test_parser_returns_sp500_rows() -> None:
    rows = _parse_sp500_table(_FAKE_HTML)
    by_ticker = {r.ticker: r for r in rows}

    assert by_ticker["AAPL"].name == "Apple Inc."
    assert by_ticker["AAPL"].sector == "Information Technology"
    assert by_ticker["AAPL"].industry_group == "Technology Hardware, Storage and Peripherals"
    assert by_ticker["AAPL"].market == "US"
    assert by_ticker["AAPL"].universe_source == US_SP500_SOURCE
    # Tickers with dots (BRK.B) preserved as-is — caller normalizes if needed.
    assert "BRK.B" in by_ticker


def test_parser_returns_empty_on_missing_table() -> None:
    rows = _parse_sp500_table("<html><body><p>no table</p></body></html>")
    assert rows == []


def test_parser_skips_short_rows() -> None:
    truncated = """
    <html><body><table id="constituents"><tbody>
      <tr><td>AAPL</td><td>Apple</td></tr>
      <tr><td>MSFT</td><td>Microsoft</td><td>IT</td><td>Software</td></tr>
    </tbody></table></body></html>
    """
    rows = _parse_sp500_table(truncated)
    assert len(rows) == 1
    assert rows[0].ticker == "MSFT"


@pytest.mark.asyncio
async def test_fetch_us_universe_returns_empty_on_network_failure() -> None:
    async def _boom(_url: str) -> str:
        raise RuntimeError("network down")

    with patch("app.services.universe.seed_us._fetch_html", side_effect=_boom):
        rows = await fetch_us_universe()

    assert rows == []
