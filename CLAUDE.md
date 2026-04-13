# CLAUDE.md

## Project Overview

StockInsight — 주식 분석 대시보드 (Next.js 15 + FastAPI + PostgreSQL)

## Quick Start

### 1. PostgreSQL 실행

Docker가 있으면:
```bash
docker-compose up -d
```

Docker 없이 직접 설치한 경우 (Windows):
```bash
# PostgreSQL 17이 설치되어 있으면 서비스가 자동 실행됨
# 확인: pg_isready -h localhost
# DB 생성 (최초 1회):
psql -U postgres -h localhost -c "CREATE DATABASE stockinsight;"
```

### 2. 백엔드

```bash
cd backend
cp .env.example .env                    # .env 없으면 복사 후 수정
uv sync --dev                           # 의존성 설치
uv run alembic upgrade head             # DB 마이그레이션
uv run python -m scripts.seed           # 시드 데이터 (최초 1회)
uv run uvicorn app.main:app --reload --port 8000
```

### 3. 프론트엔드 (별도 터미널)

```bash
cd frontend
npm install                             # 최초 1회
npm run dev
```

### 4. 접속

- 대시보드: http://localhost:3000
- API 문서: http://localhost:8000/docs
- 로그인: `.env`의 ADMIN_EMAIL / ADMIN_PASSWORD
- 종목 검색: `Cmd+K` (또는 `Ctrl+K`)

## Architecture

- 구조 문서: `docs/ARCHITECTURE.md`
- 업무 목록: `docs/tasks.md`

## Backend (FastAPI)

- Python 3.12, async SQLAlchemy + asyncpg
- 엔트리포인트: `backend/app/main.py`
- API 라우터: `backend/app/api/`
- DB 모델: `backend/app/models/`
- 데이터 수집: `backend/app/collectors/` (외부 API 호출은 항상 mock 테스트)
- 설정: `backend/app/config.py` (pydantic-settings, `.env` 파일 참조)

### 패키지 관리

- uv (`pyproject.toml` + `uv.lock`)
- 의존성 추가: `cd backend && uv add <package>`
- dev 의존성 추가: `cd backend && uv add --group dev <package>`

### 테스트

```bash
cd backend && uv run python -m pytest tests/ -v --cov=app
```

- 외부 API 호출 함수(fetch_*)는 항상 mock 처리
- `conftest.py`에서 테스트 DB 세션 + httpx AsyncClient 제공
- greenlet concurrency 설정 필수 (`pyproject.toml`)

### DB 마이그레이션

```bash
cd backend
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

## Frontend (Next.js 15)

- `frontend/AGENTS.md` 참조: Next.js 15는 breaking change가 있으므로 `node_modules/next/dist/docs/` 확인 필수
- shadcn/ui + Tailwind CSS (다크 테마 고정)
- API 클라이언트: `frontend/src/services/api.ts`
- 타입 정의: `frontend/src/types/stock.ts`

## Coding Conventions

- 한국어 UI 텍스트, 코드/커밋 메시지는 영어
- Collector 패턴: 외부 API 실패 시 `{"xxx_synced": 0, "error": "..."}` 반환 (예외 던지지 않음)
- DB upsert: `on_conflict_do_nothing` 또는 `on_conflict_do_update` 사용
- 가격 데이터 on-demand: GET /prices 요청 시 DB에 부족하면 자동 수집

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
