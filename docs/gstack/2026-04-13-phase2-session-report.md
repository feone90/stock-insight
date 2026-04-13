# Phase 2 구현 세션 리포트 (2026-04-13)

## 요약

Phase 1(실데이터 연동) 위에 Phase 2(LLM 키워드 자동생성 파이프라인)를 설계하고 구현했다.
gstack의 `/plan-eng-review`와 `/office-hours`를 사용해 설계를 검증한 뒤, 9개 커밋으로 백엔드+프론트엔드를 구현했다.

- 총 변경: 38개 파일, +3,842줄 / -300줄
- 새 테스트: 51개 (기존 69개에 추가)
- 소요 도구: gstack `/plan-eng-review`, `/office-hours`, Claude outside voice

---

## 1. 세션 흐름

```
/plan-eng-review 시작
  |
  +-- /office-hours (inline) → Phase 2 설계 문서 생성
  |     - Builder mode 선택
  |     - 키워드 자동생성 우선 결정
  |     - Batch Analysis + Scheduler 접근법 선택
  |     - 설계 문서 adversarial review (6/10 → 8/10)
  |     - 설계 문서 APPROVED
  |
  +-- Step 0: Scope Challenge
  +-- Section 1: Architecture Review (5 issues)
  +-- Section 2: Code Quality Review (2 issues)
  +-- Section 3: Test Review (coverage diagram)
  +-- Section 4: Performance Review (1 issue)
  +-- Outside Voice (Claude subagent, 11 findings)
  +-- Cross-model tension resolution (5 decisions)
  |
  +-- 구현 시작 (커밋 1~8)
  +-- PostgreSQL 설치 + DB 셋업
  +-- 백엔드 + 프론트엔드 서버 기동 확인
```

---

## 2. gstack 스킬 사용 상세

### 2.1 `/plan-eng-review` (엔지니어링 리뷰)

Phase 1 코드 전체 + Phase 2 설계를 4개 섹션으로 리뷰했다.

**Architecture Review (5 issues)**

| # | 이슈 | 결정 |
|---|------|------|
| 1 | 테스트 DB가 개발 DB와 동일 (conftest.py) | DEFERRED → TODOS.md |
| 2 | GET /prices에서 외부 API 호출 (REST 위반) | Phase 2에서 제거 |
| 3 | /sync/all 순차 실행으로 느림 | 병렬화 (asyncio.gather + Semaphore) |
| 4 | CORS가 localhost:3000 하드코딩 | config.py로 이동 |
| 5 | Admin API에 인증 없음 | Phase 2 JWT로 해결 |

**Code Quality Review (2 issues)**

| # | 이슈 | 결정 |
|---|------|------|
| 6 | 모든 API 응답이 raw dict, Pydantic 스키마 없음 | Phase 2에서 전체 스키마 추가 |
| 7 | Stock 조회+404 패턴 6회 반복 (DRY 위반) | get_stock_or_404 dependency 추출 |

**Test Review**
- Coverage diagram 생성 (코드 경로 90%, 프론트엔드 0%)
- Phase 2 테스트 계획 15개 gap 식별
- 프론트엔드 테스트 프레임워크 시작 결정

**Performance Review (1 issue)**

| # | 이슈 | 결정 |
|---|------|------|
| 9 | 목록 엔드포인트에 페이지네이션 없음 | Phase 2에서 추가 |

### 2.2 `/office-hours` (설계 세션, inline)

`/plan-eng-review` 안에서 inline으로 실행. Phase 2 설계 문서를 생성했다.

**흐름:**
1. 목표 확인 → 빌더 모드 (가족 프로젝트, 확장 가능성)
2. 쿨한 버전 질문 → "전부 다" (키워드 + 일봉분석 + AI챗)
3. 우선순위 → 키워드 자동생성 먼저
4. 현재 상태 → 네이버 증권 + 증권사 앱 + 유튜브 (10-20분/일 소비)
5. 전제 확인 3개 (뉴스/공시로 시작, Azure OpenAI, 스케줄러 기본)
6. 접근법 선택 → Batch Analysis + Scheduler
7. Adversarial spec review → 11개 이슈 발견, 전부 수정 (6/10 → 8/10)

**사용자 피드백으로 설계 변경:**
- "세명에 연연해하지말고 확장성 염두해두고 틀을 짜야지"
  → 스케줄러 기본 + 수동 동기화 보조로 변경
- "endpoint랑 key 변경해가면서 활용가능해야해"
  → LLM 어댑터 패턴 채택

**생성 문서:** `~/.gstack/projects/feone90-stock-insight/main-design-20260413-121941.md`

### 2.3 Outside Voice (Claude subagent)

독립적인 AI 서브에이전트가 Phase 1 코드 + Phase 2 설계를 검토.
11개 이슈를 발견했고, 그 중 5개가 리뷰와 충돌(cross-model tension).

**가장 중요한 발견:**

| # | 발견 | 영향 |
|---|------|------|
| 4 | asyncio.gather()로 병렬 실행 시 공유 AsyncSession 크래시 | 런타임 버그 방지 |
| 3 | analysis API의 period_type 필터링이 실제로 안 됨 (기존 버그) | 버그 수정 |
| 2 | favorites user_id 추가가 6곳+ 수정 필요 (과소평가됨) | 정확한 스코프 산정 |
| 8 | analyses 테이블에 UniqueConstraint 없어 중복 무한 증가 | 데이터 무결성 |
| 6 | US 종목 뉴스가 Naver(한국어)만이라 LLM 품질 낮음 | yfinance 뉴스 추가 |

**해결된 tension:**
1. 병렬 sync → 종목별 별도 세션 (필수)
2. period_type 버그 → 수정 + "daily"로 정의
3. LLM 어댑터 3개 과도 → 인터페이스 + Azure만 먼저
4. US 뉴스 품질 → yfinance news 추가
5. Analysis 중복 → UniqueConstraint + delete-and-replace

---

## 3. 구현 커밋 목록

| # | 커밋 | 해시 | 내용 |
|---|------|------|------|
| 0 | chore: TODOS.md + .gitignore | ae6c96c | 엔지니어링 리뷰 산출물 |
| 1 | feat: LLM adapter | 9e3ee62 | ABC + AzureOpenAI/OpenAI 어댑터 + 프롬프트 |
| 2 | feat: analyzer pipeline | 333d628 | 뉴스/공시→키워드 분석 + period_type 버그 수정 |
| - | chore: pip→uv | 6be6adc | pyproject.toml + uv.lock |
| 3 | refactor: DRY + schemas + CORS | 1dab256 | get_stock_or_404, Pydantic 13개 모델, CORS config |
| 4 | feat: JWT auth | 1545339 | 로그인/me 엔드포인트, admin guard |
| 5 | feat: favorites user_id | b88179d | 멀티유저 즐겨찾기 (6곳 수정) |
| 6 | feat: scheduler + parallel sync | 0505970 | AsyncIOScheduler 8am/6pm, 종목별 별도 세션 |
| 7 | feat: US news | a31042e | yfinance 뉴스 수집, 시장별 라우팅 |
| 8 | feat: frontend auth + toast | 43f46d9 | 로그인 UI, toast 알림, admin 전용 동기화 |

---

## 4. 새로 추가된 파일

### 백엔드

```
backend/
├── app/
│   ├── api/auth.py              # JWT 인증 (login, me, require_admin)
│   ├── dependencies.py          # get_stock_or_404 공유 의존성
│   ├── scheduler.py             # AsyncIOScheduler (8am/6pm KST)
│   ├── schemas/stock.py         # Pydantic response 모델 13개
│   └── services/llm/
│       ├── __init__.py
│       ├── adapter.py           # LLMAdapter ABC + Azure/OpenAI 구현
│       ├── analyzer.py          # 뉴스/공시 → LLM → 키워드 생성
│       └── prompts.py           # 프롬프트 템플릿 + JSON 스키마
├── alembic/versions/
│   ├── a1b2c3d4e5f6_...py       # analyses UniqueConstraint
│   └── b2c3d4e5f6a7_...py       # favorites user_id 추가
└── tests/
    ├── test_analyzer.py         # 12 tests
    ├── test_auth.py             # 15 tests
    ├── test_llm.py              # 12 tests
    ├── test_scheduler.py        # 6 tests
    └── test_us_news.py          # 7 tests (총 51개 신규)
```

### 프론트엔드

```
frontend/src/
├── components/ui/toast.tsx      # Toast 알림 컴포넌트
└── services/auth.ts             # 로그인/로그아웃/토큰 관리
```

### 수정된 주요 파일

```
backend/app/config.py            # LLM, scheduler, auth, CORS 설정 추가
backend/app/main.py              # 스케줄러 lifespan, auth 라우터
backend/app/api/admin.py         # LLM 분석 연동, admin guard, 병렬 sync
backend/app/api/stocks.py        # get_stock_or_404, response_model, on-demand sync 제거
backend/app/api/favorites.py     # user_id 스코핑
backend/app/api/analysis.py      # period_type 필터 버그 수정
backend/app/collectors/news.py   # US 종목 yfinance 뉴스 추가
backend/app/models/favorite.py   # user_id 컬럼 + UniqueConstraint 변경
backend/app/models/analysis.py   # UniqueConstraint 추가
frontend/src/services/api.ts     # auth 헤더 전송
frontend/src/components/layout/top-nav.tsx    # 로그인 UI, toast, admin 조건부 렌더
frontend/src/components/stock/stock-header.tsx # toast, admin 동기화 조건부
```

---

## 5. 아키텍처 변경

### Before (Phase 1)
```
Frontend → REST API → Collectors → DB
                                    ↑
                          수동 동기화 버튼
```

### After (Phase 2)
```
Frontend (+ auth) → REST API (+ JWT guard) → DB
                         ↑
              ┌──────────┴──────────┐
         Scheduler              Admin (manual)
         8am/6pm KST           admin only
              │                      │
    ┌─────────┴─────────┐    ┌──────┴──────┐
    │ Collectors (병렬)  │    │ Collectors  │
    │ + LLM Analyzer    │    │ + Analyzer  │
    │ 종목별 별도 세션    │    │             │
    └───────────────────┘    └─────────────┘
```

---

## 6. 환경 설정

### 패키지 관리: pip → uv 전환

```bash
cd backend
uv sync --dev           # 의존성 설치
uv run uvicorn ...      # 서버 실행
uv run python -m pytest # 테스트
uv add <package>        # 패키지 추가
```

### .env 필수 설정

```env
DATABASE_URL=postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight?ssl=disable
ADMIN_EMAIL=admin@stockinsight.local
ADMIN_PASSWORD=admin1234
JWT_SECRET=change-me-in-production

# 데이터 수집 (선택)
NAVER_CLIENT_ID=     # 한국 뉴스 수집
NAVER_CLIENT_SECRET=
DART_API_KEY=        # 한국 공시 수집

# LLM 분석 (선택)
LLM_PROVIDER=azure_openai
LLM_ENDPOINT=https://your-resource.openai.azure.com
LLM_API_KEY=your-key
LLM_DEPLOYMENT=your-deployment-name
```

### DB 셋업

```bash
# PostgreSQL 17 설치됨 (winget install PostgreSQL.PostgreSQL.17)
# 비밀번호: admin123!
# DB 생성 완료: stockinsight

cd backend
uv run alembic upgrade head    # 마이그레이션 (4개)
uv run python -m scripts.seed  # 시드 데이터
```

---

## 7. 남은 작업

### 즉시 필요
- [ ] `.env`에 API 키 설정 (Naver, DART, Azure OpenAI)
- [ ] 실제 데이터로 동기화 테스트
- [ ] ARCHITECTURE.md 업데이트 (Phase 2 반영)

### 커밋 9 (미구현)
- [ ] 프론트엔드 테스트 프레임워크 설정 (Vitest + React Testing Library)
- [ ] 핵심 컴포넌트 테스트 (PriceChart, StockSearch, auth flow)

### TODOS.md
- [ ] 테스트 DB 격리 (conftest.py 트랜잭션 롤백)
- [ ] alert() → toast 교체 (완료됨, TODOS에서 제거 가능)

### Phase 2 후속
- [ ] 페이지네이션 (news, disclosures 엔드포인트)
- [ ] AI 대화형 챗 인터페이스 (Phase 2.5)
- [ ] KR 재무지표 DART 파싱 (Phase 3)
- [ ] 스케줄러 실제 활성화 (SCHEDULER_ENABLED=true)

---

## 8. gstack 설계 문서 위치

| 문서 | 경로 |
|------|------|
| Phase 2 설계 | `~/.gstack/projects/feone90-stock-insight/main-design-20260413-121941.md` |
| 테스트 계획 | `~/.gstack/projects/feone90-stock-insight/main-eng-review-test-plan-20260413.md` |
| 체크포인트 | `~/.gstack/projects/feone90-stock-insight/checkpoints/main-checkpoint-20260413-112812.md` |
| 리뷰 로그 | `~/.gstack/projects/feone90-stock-insight/timeline.jsonl` |
| 학습 기록 | `~/.gstack/projects/feone90-stock-insight/learnings.jsonl` |

---

## 9. coworker를 위한 빠른 시작

```bash
# 1. 의존성
cd backend && uv sync --dev

# 2. DB (PostgreSQL 17이 이미 설치됨)
uv run alembic upgrade head

# 3. .env 설정 (위 섹션 6 참조)

# 4. 백엔드 실행
uv run uvicorn app.main:app --reload --port 8000

# 5. 프론트엔드 실행
cd ../frontend && npm install && npm run dev

# 6. 로그인
# admin@stockinsight.local / admin1234

# 7. 테스트
cd ../backend && uv run python -m pytest tests/ -v
# (DB 연결 필요한 테스트는 PostgreSQL 실행 중이어야 함)
```
