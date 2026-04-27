"""Auth 테스트."""

from unittest.mock import patch

import pytest

from app.api.auth import create_token, decode_token, _verify_user


TEST_EMAIL = "admin@test.com"
TEST_PASSWORD = "testpass123"


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.api.auth.settings") as mock:
        mock.admin_email = TEST_EMAIL
        mock.admin_password = TEST_PASSWORD
        mock.jwt_secret = "test-secret-key"
        mock.jwt_expire_hours = 24
        mock.dev_mode = False  # Without this, MagicMock returns truthy and bypasses auth.
        yield mock


class TestVerifyUser:
    def test_valid_credentials(self):
        user = _verify_user(TEST_EMAIL, TEST_PASSWORD)
        assert user is not None
        assert user["email"] == TEST_EMAIL
        assert user["role"] == "admin"

    def test_wrong_password(self):
        assert _verify_user(TEST_EMAIL, "wrongpass") is None

    def test_unknown_email(self):
        assert _verify_user("unknown@test.com", TEST_PASSWORD) is None

    def test_empty_admin_config(self, mock_settings):
        mock_settings.admin_email = ""
        mock_settings.admin_password = ""
        assert _verify_user(TEST_EMAIL, TEST_PASSWORD) is None


class TestJwtToken:
    def test_create_and_decode(self):
        token = create_token(TEST_EMAIL, "admin")
        payload = decode_token(token)
        assert payload["sub"] == TEST_EMAIL
        assert payload["role"] == "admin"
        assert "exp" in payload

    def test_invalid_token(self):
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_token("invalid.token.here")


class TestLoginEndpoint:
    @pytest.mark.asyncio
    async def test_login_success(self, client):
        resp = await client.post("/api/auth/login", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["role"] == "admin"
        assert data["email"] == TEST_EMAIL

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client):
        resp = await client.post("/api/auth/login", json={
            "email": TEST_EMAIL, "password": "wrong",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_email(self, client):
        resp = await client.post("/api/auth/login", json={
            "email": "nobody@test.com", "password": "pass",
        })
        assert resp.status_code == 401


class TestMeEndpoint:
    @pytest.mark.asyncio
    async def test_me_authenticated(self, client):
        token = create_token(TEST_EMAIL, "admin")
        resp = await client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200
        assert resp.json()["email"] == TEST_EMAIL
        assert resp.json()["role"] == "admin"

    @pytest.mark.asyncio
    async def test_me_no_token(self, client):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_invalid_token(self, client):
        resp = await client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid.token",
        })
        assert resp.status_code == 401


class TestAdminGuard:
    @pytest.mark.asyncio
    async def test_sync_without_auth(self, client):
        resp = await client.post("/api/admin/sync/global")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_with_user_role(self, client):
        token = create_token("user@test.com", "user")
        resp = await client.post("/api/admin/sync/global", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_sync_with_admin_role(self, client):
        token = create_token(TEST_EMAIL, "admin")
        resp = await client.post("/api/admin/sync/global", headers={
            "Authorization": f"Bearer {token}",
        })
        # 200 or error from missing DB, but NOT 401/403
        assert resp.status_code not in (401, 403)
