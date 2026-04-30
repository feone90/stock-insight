#!/usr/bin/env bash
# Railway / Render / Fly entrypoint.
#
# 1. alembic upgrade — DB schema는 첫 deploy 시 빈 Postgres에 모든 migration 적용.
# 2. uvicorn — Railway가 PORT 환경변수로 동적 포트 할당. 로컬은 default 8000.
set -euo pipefail

# DB 마이그레이션 — 새 컬럼 추가가 매 deploy 시 자동 반영.
echo "[start.sh] alembic upgrade head"
alembic upgrade head

PORT="${PORT:-8000}"
echo "[start.sh] uvicorn on 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
