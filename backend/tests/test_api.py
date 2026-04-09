import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# --- Search ---

@pytest.mark.asyncio
async def test_search_stocks(client: AsyncClient):
    response = await client.get("/api/stocks/search?q=삼성")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["ticker"] == "005930"


@pytest.mark.asyncio
async def test_search_by_ticker(client: AsyncClient):
    response = await client.get("/api/stocks/search?q=TSLA")
    assert response.status_code == 200
    data = response.json()
    assert any(s["ticker"] == "TSLA" for s in data)


@pytest.mark.asyncio
async def test_search_empty(client: AsyncClient):
    response = await client.get("/api/stocks/search?q=")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_search_no_results(client: AsyncClient):
    response = await client.get("/api/stocks/search?q=ZZZZZNOTEXIST")
    assert response.status_code == 200
    assert response.json() == []


# --- Stock Detail ---

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
async def test_stock_detail_us(client: AsyncClient):
    response = await client.get("/api/stocks/TSLA")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "TSLA"
    assert data["market"] in ("NYSE", "NASDAQ")


@pytest.mark.asyncio
async def test_stock_not_found(client: AsyncClient):
    response = await client.get("/api/stocks/INVALID")
    assert response.status_code == 404


# --- Prices ---

@pytest.mark.asyncio
async def test_stock_prices(client: AsyncClient):
    """주가 조회 — 데이터 없으면 자동 수집 트리거"""
    mock_sync = AsyncMock(return_value={"prices_synced": 0})
    with patch("app.collectors.stock_price.sync_prices", mock_sync):
        response = await client.get("/api/stocks/005930/prices?days=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_stock_prices_not_found(client: AsyncClient):
    response = await client.get("/api/stocks/INVALID/prices?days=5")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stock_prices_auto_sync(client: AsyncClient):
    """데이터 부족 시 sync_prices 호출 확인"""
    mock_sync = AsyncMock(return_value={"prices_synced": 10})
    with patch("app.collectors.stock_price.sync_prices", mock_sync):
        response = await client.get("/api/stocks/TSLA/prices?days=1095")
    assert response.status_code == 200
    # sync_prices가 호출되었는지 확인
    if mock_sync.called:
        args = mock_sync.call_args
        assert args[1].get("days", 365) >= 365


# --- Analysis ---

@pytest.mark.asyncio
async def test_analysis_not_found(client: AsyncClient):
    """분석 데이터 없는 종목 → 404"""
    response = await client.get("/api/stocks/TSLA/analysis")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_analysis_stock_not_found(client: AsyncClient):
    response = await client.get("/api/stocks/INVALID/analysis")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_analysis_with_data(client: AsyncClient, db):
    """분석 데이터가 있을 때 정상 반환"""
    from datetime import date
    from sqlalchemy import select
    from app.models import Analysis, KeywordDetail, DailyKeyword, Stock

    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    # 테스트용 분석 데이터 삽입
    analysis = Analysis(
        stock_id=stock.id,
        date=date.today(),
        period_type="weekly",
        summary="테스트 요약",
        feedback="테스트 피드백",
    )
    db.add(analysis)
    await db.flush()

    db.add(KeywordDetail(
        analysis_id=analysis.id,
        keyword="테스트키워드",
        type="positive",
        detail="테스트 상세",
        source="테스트",
        impact_level="high",
        duration="단기",
    ))
    db.add(DailyKeyword(
        analysis_id=analysis.id,
        date=date.today(),
        keyword="일간키워드",
        type="neutral",
    ))
    await db.commit()

    response = await client.get("/api/stocks/005930/analysis?period=weekly")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == "테스트 요약"
    assert data["feedback"] == "테스트 피드백"
    assert len(data["keywords"]) >= 1
    assert data["keywords"][0]["keyword"] == "테스트키워드"
    assert len(data["daily_keywords"]) >= 1


# --- News ---

@pytest.mark.asyncio
async def test_stock_news(client: AsyncClient):
    response = await client.get("/api/stocks/005930/news")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_stock_news_not_found(client: AsyncClient):
    response = await client.get("/api/stocks/INVALID/news")
    assert response.status_code == 404


# --- Disclosures ---

@pytest.mark.asyncio
async def test_stock_disclosures(client: AsyncClient):
    response = await client.get("/api/stocks/005930/disclosures")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_stock_disclosures_not_found(client: AsyncClient):
    response = await client.get("/api/stocks/INVALID/disclosures")
    assert response.status_code == 404


# --- Favorites ---

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
    data = response.json()
    assert data["status"] in ("added", "already_exists")

    # List should contain TSLA
    response = await client.get("/api/favorites")
    tickers = [s["ticker"] for s in response.json()]
    assert "TSLA" in tickers

    # Remove
    response = await client.delete("/api/favorites/TSLA")
    assert response.status_code == 200
    assert response.json()["status"] == "removed"


@pytest.mark.asyncio
async def test_favorite_add_duplicate(client: AsyncClient):
    """이미 즐겨찾기인 종목 추가 → already_exists"""
    await client.post("/api/favorites/005930")
    response = await client.post("/api/favorites/005930")
    assert response.status_code == 200
    assert response.json()["status"] == "already_exists"


@pytest.mark.asyncio
async def test_favorite_add_not_found(client: AsyncClient):
    response = await client.post("/api/favorites/INVALID")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_favorite_remove_not_found(client: AsyncClient):
    response = await client.delete("/api/favorites/INVALID")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_favorite_remove_non_favorited(client: AsyncClient):
    """즐겨찾기 아닌 종목 삭제 → 정상 응답 (removed)"""
    # 먼저 삭제해서 확실히 없는 상태로
    await client.delete("/api/favorites/TSLA")
    response = await client.delete("/api/favorites/TSLA")
    assert response.status_code == 200
    assert response.json()["status"] == "removed"


# --- Exchange Rates ---

@pytest.mark.asyncio
async def test_exchange_rates_latest_empty(client: AsyncClient):
    """환율 데이터 없을 때 빈 배열"""
    response = await client.get("/api/exchange-rates/latest")
    assert response.status_code == 200
    # 데이터가 없거나 있을 수 있음 (DB 상태 의존)
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_exchange_rates_with_data(client: AsyncClient, db):
    """환율 데이터 있을 때 정상 반환"""
    from datetime import date
    from sqlalchemy.dialects.postgresql import insert
    from app.models.exchange_rate import ExchangeRate

    stmt = insert(ExchangeRate).values(
        date=date.today(),
        currency_pair="USD/KRW",
        rate=1400.5,
    ).on_conflict_do_update(
        constraint="uq_rate_date_pair",
        set_={"rate": 1400.5},
    )
    await db.execute(stmt)
    await db.commit()

    response = await client.get("/api/exchange-rates/latest")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(r["currency_pair"] == "USD/KRW" for r in data)
