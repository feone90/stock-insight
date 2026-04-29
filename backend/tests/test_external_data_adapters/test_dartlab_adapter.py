"""DartlabAdapter — spec §5 6 unit cases (mock dartlab Company)."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.external_data_adapters.cache import ResultCache
from app.services.external_data_adapters.dartlab_adapter import DartlabAdapter


def _kr_company_mock() -> MagicMock:
    c = MagicMock()
    c.stockCode = "005930"
    c.corpName = "삼성전자"
    c.market = "KR"
    c.currency = "KRW"
    c.fiscalYearEnd = "12-31"
    c.corpCode = "00126380"

    sector = MagicMock()
    sector.sector = "IT"
    sector.industryGroup = "Semiconductors"
    sector.confidence = 1.0
    c.sector = sector

    raw = MagicMock()
    raw.to_dicts.return_value = [
        {"bsns_year": "2020", "sj_div": "IS"},
        {"bsns_year": "2021", "sj_div": "IS"},
        {"bsns_year": "2022", "sj_div": "IS"},
        {"bsns_year": "2023", "sj_div": "IS"},
        {"bsns_year": "2024", "sj_div": "IS"},
        {"bsns_year": "2024", "sj_div": "BS"},  # same year, different statement
    ]
    c.rawFinance = raw
    return c


def _us_company_mock(ticker: str = "TSLA") -> MagicMock:
    c = MagicMock()
    c.stockCode = ticker
    c.corpName = "Tesla, Inc."
    c.market = "US"
    c.currency = "USD"
    c.fiscalYearEnd = None  # dartlab 0.9.26 returns None for US fiscal year
    c.cik = "0001318605"
    c.sector = None  # US sector unfilled by dartlab

    # `c.rawFinance` must raise AttributeError (real US Company has no rawFinance)
    del c.rawFinance

    c.analysis.return_value = {
        "marginTrend": {
            "history": [
                {"period": "2024", "revenue": 100,
                 "operatingIncome": 10, "operatingMargin": 10, "netIncome": 8},
                {"period": "2023", "revenue": 90,
                 "operatingIncome": 9, "operatingMargin": 10, "netIncome": 7},
            ]
        }
    }
    return c


@pytest.mark.asyncio
async def test_kr_identity_emits_full_schema():
    adapter = DartlabAdapter(cache=ResultCache())
    with patch(
        "app.services.external_data_adapters.dartlab_adapter._load_company",
        return_value=_kr_company_mock(),
    ):
        ident = await adapter.fetch_identity("005930")
    assert ident.ticker == "005930"
    assert ident.name == "삼성전자"
    assert ident.market == "KR"
    assert ident.currency == "KRW"
    assert ident.fiscal_year_end == "12-31"
    assert ident.corp_code == "00126380"
    assert ident.cik is None  # KR ticker → no CIK
    assert ident.source == "dartlab"


@pytest.mark.asyncio
async def test_kr_financials_aggregates_records_by_year():
    adapter = DartlabAdapter(cache=ResultCache())
    with patch(
        "app.services.external_data_adapters.dartlab_adapter._load_company",
        return_value=_kr_company_mock(),
    ):
        series = await adapter.fetch_financial_series("005930")
    periods = [r["period"] for r in series.rows]
    assert periods == ["2020", "2021", "2022", "2023", "2024"]
    assert series.period_type == "annual"
    assert series.source == "dartlab"
    # 2024 has 2 rows (IS + BS) — verify aggregation worked
    assert next(r for r in series.rows if r["period"] == "2024")["row_count"] == 2


@pytest.mark.asyncio
async def test_us_identity_handles_missing_fiscal_year_end_gracefully():
    adapter = DartlabAdapter(cache=ResultCache())
    with patch(
        "app.services.external_data_adapters.dartlab_adapter._load_company",
        return_value=_us_company_mock(),
    ):
        ident = await adapter.fetch_identity("TSLA")
    assert ident.market == "US"
    assert ident.fiscal_year_end is None  # SEC EDGAR adapter fills this
    assert ident.cik == "0001318605"
    assert ident.corp_code is None  # US ticker → no DART corp_code


@pytest.mark.asyncio
async def test_us_financials_via_analysis_boost_when_no_rawfinance():
    adapter = DartlabAdapter(cache=ResultCache())
    with patch(
        "app.services.external_data_adapters.dartlab_adapter._load_company",
        return_value=_us_company_mock(),
    ):
        series = await adapter.fetch_financial_series("TSLA")
    assert series.source == "dartlab"
    assert len(series.rows) == 2
    assert series.rows[0]["period"] == "2024"
    assert series.rows[0]["revenue"] == 100
    assert series.rows[0]["operating_income"] == 10


@pytest.mark.asyncio
async def test_kr_sector_passthrough_from_dartlab_sector_info():
    adapter = DartlabAdapter(cache=ResultCache())
    with patch(
        "app.services.external_data_adapters.dartlab_adapter._load_company",
        return_value=_kr_company_mock(),
    ):
        sector = await adapter.fetch_sector("005930")
    assert sector is not None
    assert sector.sector == "IT"
    assert sector.industry_group == "Semiconductors"
    assert sector.confidence == 1.0
    assert sector.source == "dartlab"


@pytest.mark.asyncio
async def test_dartlab_attribute_disappearance_propagates_error():
    """Adversarial — dartlab 0.9.X 패치로 expected attribute 사라짐.

    Adapter는 silent fallback X — 명시적 AttributeError가 caller까지 propagate
    되어야 하고, log + alert hook이 발화 (alert hook은 P1.6에서 본격 wire).
    """
    broken = _kr_company_mock()
    del broken.corpName  # simulate 0.9.X breaking change

    adapter = DartlabAdapter(cache=ResultCache())
    with patch(
        "app.services.external_data_adapters.dartlab_adapter._load_company",
        return_value=broken,
    ):
        with pytest.raises(AttributeError):
            await adapter.fetch_identity("005930")
