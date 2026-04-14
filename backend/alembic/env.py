from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# asyncpg URL → psycopg2 sync URL (Alembic은 sync 드라이버 필요)
# Also strip ?ssl=disable (asyncpg param) and replace with sslmode=disable for psycopg2
_url = settings.database_url.replace("+asyncpg", "")
if "?ssl=disable" in _url:
    _url = _url.replace("?ssl=disable", "") + "?sslmode=disable"
elif "&ssl=disable" in _url:
    _url = _url.replace("&ssl=disable", "") + "&sslmode=disable"
sync_url = _url


def run_migrations_offline() -> None:
    context.configure(url=sync_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(sync_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
