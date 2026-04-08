import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_search_stocks(client: AsyncClient):
    response = await client.get("/api/stocks/search?q=삼성")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["ticker"] == "005930"


@pytest.mark.asyncio
async def test_search_empty(client: AsyncClient):
    response = await client.get("/api/stocks/search?q=")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_stock_detail(client: AsyncClient):
    response = await client.get("/api/stocks/005930")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "005930"
    assert data["name"] == "삼성전자"
    assert "is_favorite" in data
    assert "stats" in data


@pytest.mark.asyncio
async def test_stock_not_found(client: AsyncClient):
    response = await client.get("/api/stocks/INVALID")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stock_prices(client: AsyncClient):
    response = await client.get("/api/stocks/005930/prices?days=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert "date" in data[0]
    assert "open" in data[0]
    assert "close" in data[0]


@pytest.mark.asyncio
async def test_analysis(client: AsyncClient):
    response = await client.get("/api/stocks/005930/analysis")
    assert response.status_code == 200
    data = response.json()
    assert "keywords" in data
    assert "daily_keywords" in data
    assert "summary" in data
    assert "feedback" in data
    assert len(data["keywords"]) >= 1


@pytest.mark.asyncio
async def test_favorites_list(client: AsyncClient):
    response = await client.get("/api/favorites")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_favorite_add_remove(client: AsyncClient):
    # Add
    response = await client.post("/api/favorites/TSLA")
    assert response.status_code == 200

    # List should contain TSLA
    response = await client.get("/api/favorites")
    tickers = [s["ticker"] for s in response.json()]
    assert "TSLA" in tickers

    # Remove
    response = await client.delete("/api/favorites/TSLA")
    assert response.status_code == 200
    assert response.json()["status"] == "removed"
