#!/bin/bash
# 백엔드 개발 서버 실행
# Usage: ./scripts/dev-backend.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$ROOT_DIR/backend"

# 색상
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== StockInsight Backend ===${NC}"

# 1. PostgreSQL 확인
echo -e "${YELLOW}[1/4] PostgreSQL 확인...${NC}"
if ! pg_isready -h localhost -p 5432 -q 2>/dev/null; then
    echo -e "${YELLOW}  PostgreSQL이 꺼져있습니다. docker-compose로 시작합니다...${NC}"
    docker-compose -f "$ROOT_DIR/docker-compose.yml" up -d db
    echo "  DB 준비 대기 중..."
    sleep 3
fi
echo -e "${GREEN}  PostgreSQL OK${NC}"

# 2. venv 활성화
echo -e "${YELLOW}[2/4] 가상환경 활성화...${NC}"
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo -e "${RED}  venv가 없습니다. 먼저 생성하세요:${NC}"
    echo "  cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi
source "$BACKEND_DIR/venv/bin/activate"
echo -e "${GREEN}  venv OK${NC}"

# 3. 마이그레이션
echo -e "${YELLOW}[3/4] DB 마이그레이션...${NC}"
cd "$BACKEND_DIR"
alembic upgrade head
echo -e "${GREEN}  마이그레이션 OK${NC}"

# 4. 서버 실행
echo -e "${YELLOW}[4/4] 서버 시작 (port 8000)...${NC}"
echo -e "${GREEN}  http://localhost:8000/docs${NC}"
echo ""
uvicorn app.main:app --reload --port 8000
