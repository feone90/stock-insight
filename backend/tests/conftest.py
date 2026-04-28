"""Test configuration — isolated test DB with per-test transaction rollback."""

import asyncio
import os

# Override env BEFORE importing anything from `app` so settings doesn't pick up
# real .env values (DEV_MODE bypass, real API keys, etc.) and tests stay
# hermetic regardless of the developer's local .env.
_TEST_ENV_OVERRIDES = {
    "DEV_MODE": "false",
    "DART_API_KEY": "",
    "NAVER_CLIENT_ID": "",
    "NAVER_CLIENT_SECRET": "",
    "NEWSAPI_KEY": "",
    "LLM_API_KEY": "",
    "LLM_ENDPOINT": "",
    "LLM_DEPLOYMENT": "",
    "LLM_MODEL": "",
    "ADMIN_EMAIL": "",
    "ADMIN_PASSWORD": "",
    "SCHEDULER_ENABLED": "false",
}
for _k, _v in _TEST_ENV_OVERRIDES.items():
    os.environ[_k] = _v

from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import Base  # noqa: E402

# Test DB: stockinsight_test (dev DB = stockinsight)
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    settings.database_url.replace("/stockinsight", "/stockinsight_test"),
)

test_engine = create_async_engine(TEST_DB_URL, echo=False)
test_session_factory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Create schema + seed once per test session."""
    # 1. Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 2. Seed test data (monkey-patch async_session temporarily)
    import app.database as db_module

    original_session = db_module.async_session
    db_module.async_session = test_session_factory
    try:
        from scripts.seed import seed

        await seed()
    finally:
        db_module.async_session = original_session

    yield

    await test_engine.dispose()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Per-test isolated session. Rolls back all writes after each test."""
    connection = await test_engine.connect()
    trans = await connection.begin()

    session = AsyncSession(bind=connection, expire_on_commit=False)
    await connection.begin_nested()  # SAVEPOINT

    # Re-create SAVEPOINT after each session.commit() so outer trans stays open
    @event.listens_for(session.sync_session, "after_transaction_end")
    def restart_savepoint(sess, transaction):
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    yield session

    await session.close()
    await trans.rollback()
    await connection.close()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.database import get_db
    from app.main import app

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
