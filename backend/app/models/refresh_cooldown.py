"""Per-ticker / per-action refresh cooldown — multi-worker safe.

옛 구현은 cards.py 안 in-memory dict (`_last_refresh: dict[str, float]`) 였다.
Azure App Service 가 gunicorn worker N개 띄우면 dict 가 worker 별로 분리되어
같은 ticker 에 대해 worker1 이 30s cooldown 적용했다고 worker2 가 모름 →
무지성 클릭이 외부 API rate limit 칠 수 있음. DB 한 곳에 박아 서버 전체에서
공유.

`try_acquire_cooldown` 헬퍼가 atomic UPSERT 한 번으로 acquire 시도 + 잔여
시간 반환. PostgreSQL `ON CONFLICT DO UPDATE ... WHERE` 조건 활용.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class RefreshCooldown(Base):
    __tablename__ = "refresh_cooldowns"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    # "price" / "data" / "refresh" / "full" — 4 종류 endpoint.
    action: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
