import pytest
from unittest.mock import patch, AsyncMock


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Admin tests don't exercise auth — they assume DEV_MODE bypass.
    Auth-specific assertions live in test_auth.py."""
    with patch("app.api.auth.settings") as s:
        s.dev_mode = True
        s.admin_email = "admin@test.com"
        s.admin_password = "test"
        s.jwt_secret = "test-secret"
        s.jwt_expire_hours = 24
        yield s


@pytest.mark.asyncio
async def test_sync_stock(client):
    """종목별 동기화 API.

    NOTE: setup 단계에서 'Future attached to a different loop' RuntimeError가
    간헐적으로 발생 — 파일 내 첫 async 테스트가 session-scoped engine과
    function-scoped event loop 간 mismatch로 깨지는 패턴. 같은 엔드포인트의
    error-path 검증은 test_sync_stock_with_errors가 커버. fixture 인프라 fix는
    TODOS.md 참조.
    """
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
    assert data["ticker"] == "005930"
    assert data["synced"]["prices"] == 10
    assert data["synced"]["financials"] == 1
    assert data["synced"]["news"] == 5
    assert data["synced"]["disclosures"] == 3
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_sync_stock_with_errors(client):
    """동기화 시 일부 실패 → errors 배열에 포함"""
    with patch("app.api.admin.sync_prices", new_callable=AsyncMock, return_value={"prices_synced": 5}), \
         patch("app.api.admin.sync_financials", new_callable=AsyncMock, return_value={"financials_synced": 0, "error": "재무 데이터 없음"}), \
         patch("app.api.admin.sync_news", new_callable=AsyncMock, return_value={"news_synced": 0, "error": "Naver API 키 미설정"}), \
         patch("app.api.admin.sync_disclosures", new_callable=AsyncMock, return_value={"disclosures_synced": 0}):
        resp = await client.post("/api/admin/sync/stock/005930")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["errors"]) == 2
    assert data["synced"]["prices"] == 5


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
    assert data["synced"]["exchange_rates"] == 3
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_sync_global_with_error(client):
    """글로벌 동기화 실패 시 에러 포함"""
    with patch("app.api.admin.sync_exchange_rates", new_callable=AsyncMock,
               return_value={"exchange_rates_synced": 0, "error": "환율 조회 실패"}):
        resp = await client.post("/api/admin/sync/global")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["errors"]) == 1


@pytest.mark.asyncio
async def test_sync_all(client):
    """전체 동기화 API (즐겨찾기 종목 + 글로벌)"""
    with patch("app.api.admin.sync_prices", new_callable=AsyncMock, return_value={"prices_synced": 10}), \
         patch("app.api.admin.sync_financials", new_callable=AsyncMock, return_value={"financials_synced": 1}), \
         patch("app.api.admin.sync_news", new_callable=AsyncMock, return_value={"news_synced": 5}), \
         patch("app.api.admin.sync_disclosures", new_callable=AsyncMock, return_value={"disclosures_synced": 0}), \
         patch("app.api.admin.sync_exchange_rates", new_callable=AsyncMock, return_value={"exchange_rates_synced": 3}):
        resp = await client.post("/api/admin/sync/all")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["global_synced"] is True
    assert isinstance(data["stocks_synced"], list)
    assert data["total_synced"]["exchange_rates"] == 3


@pytest.mark.asyncio
async def test_sync_all_with_errors(client):
    """전체 동기화 시 일부 종목 에러"""
    with patch("app.api.admin.sync_prices", new_callable=AsyncMock,
               return_value={"prices_synced": 0, "error": "주가 조회 실패"}), \
         patch("app.api.admin.sync_financials", new_callable=AsyncMock, return_value={"financials_synced": 0}), \
         patch("app.api.admin.sync_news", new_callable=AsyncMock, return_value={"news_synced": 0}), \
         patch("app.api.admin.sync_disclosures", new_callable=AsyncMock, return_value={"disclosures_synced": 0}), \
         patch("app.api.admin.sync_exchange_rates", new_callable=AsyncMock, return_value={"exchange_rates_synced": 3}):
        resp = await client.post("/api/admin/sync/all")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["errors"]) >= 1


@pytest.mark.asyncio
async def test_sync_all_exchange_rate_error(client):
    """전체 동기화 시 환율 수집 에러"""
    with patch("app.api.admin.sync_prices", new_callable=AsyncMock, return_value={"prices_synced": 0}), \
         patch("app.api.admin.sync_financials", new_callable=AsyncMock, return_value={"financials_synced": 0}), \
         patch("app.api.admin.sync_news", new_callable=AsyncMock, return_value={"news_synced": 0}), \
         patch("app.api.admin.sync_disclosures", new_callable=AsyncMock, return_value={"disclosures_synced": 0}), \
         patch("app.api.admin.sync_exchange_rates", new_callable=AsyncMock,
               return_value={"exchange_rates_synced": 0, "error": "환율 API 오류"}):
        resp = await client.post("/api/admin/sync/all")

    assert resp.status_code == 200
    data = resp.json()
    assert any("환율" in e for e in data["errors"])
