import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_sync_stock(client):
    """종목별 동기화 API"""
    mock_results = {
        "prices": {"prices_synced": 10},
        "financials": {"financials_synced": 1},
        "news": {"news_synced": 5},
        "disclosures": {"disclosures_synced": 3},
    }

    with patch("app.api.admin.sync_prices", new_callable=AsyncMock, return_value=mock_results["prices"]), \
         patch("app.api.admin.sync_financials", new_callable=AsyncMock, return_value=mock_results["financials"]), \
         patch("app.api.admin.sync_news", new_callable=AsyncMock, return_value=mock_results["news"]), \
         patch("app.api.admin.sync_disclosures", new_callable=AsyncMock, return_value=mock_results["disclosures"]):
        resp = await client.post("/api/admin/sync/stock/005930")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "synced" in data


@pytest.mark.asyncio
async def test_sync_stock_not_found(client):
    """존재하지 않는 종목 동기화 시 404"""
    resp = await client.post("/api/admin/sync/stock/INVALID")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_global(client):
    """글로벌 동기화 API"""
    mock_result = {"exchange_rates_synced": 3}

    with patch("app.api.admin.sync_exchange_rates", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.post("/api/admin/sync/global")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
