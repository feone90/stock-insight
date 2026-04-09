#!/bin/bash
# 백엔드 + 프론트엔드 동시 실행
# Usage: ./scripts/dev-all.sh
# Ctrl+C로 둘 다 종료

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# 색상
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cleanup() {
    echo ""
    echo -e "${YELLOW}서버 종료 중...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}종료 완료${NC}"
}
trap cleanup EXIT

echo -e "${GREEN}=== StockInsight Dev (Backend + Frontend) ===${NC}"

# 1. PostgreSQL
echo -e "${YELLOW}[1/4] PostgreSQL 확인...${NC}"
if ! pg_isready -h localhost -p 5432 -q 2>/dev/null; then
    docker-compose -f "$ROOT_DIR/docker-compose.yml" up -d db
    sleep 3
fi
echo -e "${GREEN}  PostgreSQL OK${NC}"

# 2. venv + 마이그레이션
echo -e "${YELLOW}[2/4] 백엔드 준비...${NC}"
source "$ROOT_DIR/backend/venv/bin/activate"
cd "$ROOT_DIR/backend"
alembic upgrade head 2>&1 | tail -1
echo -e "${GREEN}  마이그레이션 OK${NC}"

# 3. 백엔드 시작 (백그라운드)
echo -e "${YELLOW}[3/4] 백엔드 시작 (port 8000)...${NC}"
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
sleep 2

# 헬스체크
if ! curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "${RED}  백엔드 시작 실패${NC}"
    exit 1
fi
echo -e "${GREEN}  백엔드 OK${NC}"

# 4. 프론트엔드 시작 (백그라운드)
echo -e "${YELLOW}[4/4] 프론트엔드 시작 (port 3000)...${NC}"
cd "$ROOT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  백엔드:    http://localhost:8000/docs${NC}"
echo -e "${GREEN}  프론트엔드: http://localhost:3000${NC}"
echo -e "${GREEN}  종료: Ctrl+C${NC}"
echo -e "${GREEN}============================================${NC}"

wait
