# CLAUDE.md

## Project Overview

StockInsight — 주식 분석 대시보드 (Next.js 16 + FastAPI + PostgreSQL + Azure OpenAI)

대시보드(차트/키워드/AI 분석) + `/chat` 대화형 에이전트(자연어 질문 → DB tool-calling 응답).

## Quick Start

```bash
# 1. DB (PostgreSQL 17 설치 필요)
pg_isready -h localhost || echo "PostgreSQL 실행 필요"

# 2. 백엔드
cd backend
cp .env.example .env              # 최초: .env 생성 후 API 키 설정
uv sync --dev                     # 의존성 설치
uv run alembic upgrade head       # DB 마이그레이션
uv run python -m scripts.seed     # 시드 데이터 (최초 1회)
uv run uvicorn app.main:app --reload --port 8000

# 3. 프론트엔드 (별도 터미널)
cd frontend && npm install && npm run dev

# 4. 접속: http://localhost:3000 | API docs: http://localhost:8000/docs
# 5. 로그인: .env의 ADMIN_EMAIL / ADMIN_PASSWORD
# 6. 종목 검색: Ctrl+K
```

## Docs Index

| 문서 | 내용 |
|------|------|
| `docs/ARCHITECTURE.md` | 디렉토리 구조, 데이터 흐름, DB 테이블, API 엔드포인트 |
| `docs/tasks.md` | Phase 0~3 작업 현황 (체크리스트) |
| `docs/integrations.md` | 외부 API 연동 상세 (인증, 제한사항, 발급 방법) |
| `docs/gstack/` | gstack 세션 리포트 |
| `TODOS.md` | 당장 해야 할 항목 |
| `backend/.env.example` | 환경변수 템플릿 |

## Backend

- **패키지 관리:** uv (`pyproject.toml` + `uv.lock`)
- **테스트:** `cd backend && uv run python -m pytest tests/ -v --cov=app`
- **마이그레이션:** `cd backend && uv run alembic revision --autogenerate -m "desc"`
- **의존성 추가:** `uv add <pkg>` / `uv add --group dev <pkg>`

### 주요 디렉토리

| 경로 | 역할 |
|------|------|
| `app/api/` | FastAPI 라우터 (stocks, analysis, favorites, admin, auth, exchange_rates, chat) |
| `app/models/` | SQLAlchemy ORM 모델 |
| `app/collectors/` | 외부 데이터 수집 (주가, 뉴스, 공시, 재무, 환율) |
| `app/services/llm/` | LLM 어댑터 + 분석 파이프라인 |
| `app/services/chat/` | Chat agent (3 tools + SSE 스트리밍 오케스트레이터) |
| `app/scheduler.py` | APScheduler (8am/6pm KST 자동 동기화) |
| `app/schemas/` | Pydantic response 모델 |
| `app/dependencies.py` | 공유 의존성 (get_stock_or_404) |

## Frontend

- Next.js 16 + React 19 + shadcn/ui + Tailwind CSS (다크 테마)
- `frontend/AGENTS.md` 참조: Next.js breaking change 있으므로 `node_modules/next/dist/docs/` 확인
- API 클라이언트: `frontend/src/services/api.ts`
- Auth 관리: `frontend/src/services/auth.ts`

## Coding Conventions

- 한국어 UI 텍스트, 코드/커밋 메시지는 영어
- Collector 패턴: 외부 API 실패 시 `{"xxx_synced": 0, "error": "..."}` 반환 (예외 던지지 않음)
- Chat tool 패턴: 성공 시 dict, 알려진 실패 시 `{"error": "..."}` (예외 던지지 않음)
- DB upsert: `on_conflict_do_nothing` 또는 `on_conflict_do_update`
- LLM 분석: 동기화 시 자동 실행 (llm_api_key 설정 시)
