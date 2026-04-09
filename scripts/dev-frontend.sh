#!/bin/bash
# 프론트엔드 개발 서버 실행
# Usage: ./scripts/dev-frontend.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$ROOT_DIR/frontend"

# 색상
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== StockInsight Frontend ===${NC}"

# 1. 백엔드 헬스체크
echo -e "${YELLOW}[1/3] 백엔드 확인...${NC}"
if ! curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "${RED}  백엔드가 응답하지 않습니다 (localhost:8000)${NC}"
    echo "  먼저 실행하세요: ./scripts/dev-backend.sh"
    exit 1
fi
echo -e "${GREEN}  백엔드 OK${NC}"

# 2. 의존성 확인
echo -e "${YELLOW}[2/3] 의존성 확인...${NC}"
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    echo "  npm install 실행 중..."
    npm install
fi
echo -e "${GREEN}  의존성 OK${NC}"

# 3. 서버 실행
echo -e "${YELLOW}[3/3] 서버 시작 (port 3000)...${NC}"
echo -e "${GREEN}  http://localhost:3000${NC}"
echo ""
npm run dev
