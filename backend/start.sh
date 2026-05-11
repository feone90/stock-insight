#!/usr/bin/env bash
# Container entrypoint (Azure App Service / Railway / Render).
#
# 1. alembic upgrade — schema 첫 deploy 시 빈 Postgres에 모든 migration 적용.
# 2. universe seed (background, idempotent) — 빈 DB 첫 시작 시 KR/US tier=1
#    종목 자동 채움. 이미 채워졌으면 빠른 no-op. uvicorn 시작을 막지 않도록
#    background로 실행.
# 3. uvicorn — Azure가 PORT env로 동적 포트 할당. 로컬은 default 8000.
set -euo pipefail

echo "[start.sh] alembic upgrade head"
alembic upgrade head

echo "[start.sh] universe seed (background, idempotent)"
(python -m scripts.seed_universe 2>&1 | sed 's/^/[seed] /' || echo "[seed] non-fatal failure") &

PORT="${PORT:-8000}"
echo "[start.sh] uvicorn on 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
