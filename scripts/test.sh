#!/bin/bash
# 백엔드 테스트 실행
# Usage: ./scripts/test.sh          (전체 테스트 + 커버리지)
#        ./scripts/test.sh -k sync  (키워드 필터)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$ROOT_DIR/backend"

# 색상
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== StockInsight Tests ===${NC}"

source "$BACKEND_DIR/venv/bin/activate"
cd "$BACKEND_DIR"

echo -e "${YELLOW}pytest 실행 중...${NC}"
echo ""
python -m pytest tests/ -v --cov=app --cov-report=term-missing "$@"
