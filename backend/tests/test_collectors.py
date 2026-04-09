from app.config import Settings


def test_settings_defaults():
    s = Settings(database_url="postgresql+asyncpg://test:test@localhost/test")
    assert s.dart_api_key == ""
    assert s.naver_client_id == ""
    assert s.naver_client_secret == ""
