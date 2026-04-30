"""KR universe seed — `dartlab.listing()` mocked at `_fetch_listing_records`."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.universe.seed_kr import (
    KR_KOSDAQ_SOURCE,
    KR_KOSPI_SOURCE,
    fetch_kr_universe,
)

# Sample matches the actual dartlab schema (verified 2026-04-30, polars to_dicts).
_FAKE_LISTING = [
    {
        "회사명": "삼성전자",
        "시장구분": "유가",
        "종목코드": "005930",
        "업종": "반도체 제조업",
        "주요제품": "반도체, 휴대폰",
        "상장일": "1975-06-11",
        "결산월": "12월",
        "대표자명": "한종희",
        "홈페이지": "https://www.samsung.com",
        "지역": "경기도",
    },
    {
        "회사명": "셀트리온",
        "시장구분": "유가",
        "종목코드": "068270",
        "업종": "의약품 제조업",
        "주요제품": "바이오시밀러",
        "상장일": "2008-08-22",
        "결산월": "12월",
        "대표자명": "기우성",
        "홈페이지": None,
        "지역": "인천광역시",
    },
    {
        "회사명": "에코프로비엠",
        "시장구분": "코스닥",
        "종목코드": "247540",
        "업종": "전자부품 제조업",
        "주요제품": "양극재",
        "상장일": "2019-03-05",
        "결산월": "12월",
        "대표자명": "주재환",
        "홈페이지": None,
        "지역": "충청북도",
    },
    {
        "회사명": "코넥스테스트",
        "시장구분": "코넥스",
        "종목코드": "999990",
        "업종": "기타",
        "주요제품": "n/a",
        "상장일": "2024-01-01",
        "결산월": "12월",
        "대표자명": "테스트",
        "홈페이지": None,
        "지역": "서울",
    },
]


@pytest.mark.asyncio
async def test_kr_universe_normalizes_kospi_kosdaq() -> None:
    with patch(
        "app.services.universe.seed_kr._fetch_listing_records",
        return_value=_FAKE_LISTING,
    ):
        rows = await fetch_kr_universe()

    by_ticker = {r.ticker: r for r in rows}
    assert "005930" in by_ticker
    assert by_ticker["005930"].market == "KOSPI"
    assert by_ticker["005930"].universe_source == KR_KOSPI_SOURCE
    assert by_ticker["005930"].sector == "반도체 제조업"
    assert by_ticker["005930"].listing_date == "1975-06-11"

    assert "247540" in by_ticker
    assert by_ticker["247540"].market == "KOSDAQ"
    assert by_ticker["247540"].universe_source == KR_KOSDAQ_SOURCE


@pytest.mark.asyncio
async def test_kr_universe_drops_konex() -> None:
    with patch(
        "app.services.universe.seed_kr._fetch_listing_records",
        return_value=_FAKE_LISTING,
    ):
        rows = await fetch_kr_universe()

    tickers = {r.ticker for r in rows}
    assert "999990" not in tickers, "KONEX (코넥스) must be excluded from Tier 1"


@pytest.mark.asyncio
async def test_kr_universe_returns_empty_on_dartlab_failure() -> None:
    def _boom() -> list[dict]:
        raise RuntimeError("dartlab unavailable")

    with patch(
        "app.services.universe.seed_kr._fetch_listing_records",
        side_effect=_boom,
    ):
        rows = await fetch_kr_universe()

    assert rows == []


@pytest.mark.asyncio
async def test_kr_universe_skips_invalid_rows() -> None:
    bad_rows = [
        {"시장구분": "유가", "종목코드": "", "회사명": "Empty ticker"},  # empty ticker
        {"시장구분": "유가", "종목코드": "111111"},  # missing name
        {"시장구분": None, "종목코드": "222222", "회사명": "No segment"},
        {"시장구분": "유가", "종목코드": "333333", "회사명": "Valid"},
    ]
    with patch(
        "app.services.universe.seed_kr._fetch_listing_records",
        return_value=bad_rows,
    ):
        rows = await fetch_kr_universe()

    assert len(rows) == 1
    assert rows[0].ticker == "333333"
    assert rows[0].sector == "Unknown"
