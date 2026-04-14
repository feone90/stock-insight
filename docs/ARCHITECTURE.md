# StockInsight - 아키텍처

주식 분석 대시보드. 뉴스/공시를 LLM이 분석하여 상승/하락 키워드를 자동 생성.

## 기술 스택

| 계층 | 기술 |
|------|------|
| 프론트엔드 | Next.js 16, React 19, Tailwind CSS, shadcn/ui, lightweight-charts v5 |
| 백엔드 | FastAPI, SQLAlchemy 2.0 (async), Alembic, APScheduler |
| DB | PostgreSQL 17 (asyncpg) |
| LLM | Azure AI Foundry (Responses API), 어댑터 패턴으로 교체 가능 |
| 데이터 수집 | yfinance, FinanceDataReader, Naver News, NewsAPI.org, DART |
| 패키지 관리 | uv (backend), npm (frontend) |
| 인증 | JWT (python-jose) |

## 디렉토리 구조

```
stock-insight/
├── backend/
│   ├── app/
│   │   ├── api/                    # FastAPI 라우터
│   │   │   ├── admin.py            # POST /api/admin/sync/* (관리자 전용)
│   │   │   ├── analysis.py         # GET /api/stocks/{ticker}/analysis
│   │   │   ├── auth.py             # POST /api/auth/login, GET /api/auth/me
│   │   │   ├── exchange_rates.py   # GET /api/exchange-rates/latest
│   │   │   ├── favorites.py        # GET/POST/DELETE /api/favorites
│   │   │   └── stocks.py           # GET /api/stocks/* (검색, 상세, 가격, 뉴스, 공시)
│   │   ├── collectors/             # 외부 데이터 수집
│   │   │   ├── stock_price.py      # yfinance (US) / FinanceDataReader (KR)
│   │   │   ├── stock_lookup.py     # 종목 검색 + 자동등록 (yfinance/FDR)
│   │   │   ├── financials.py       # yfinance (US) / DART (KR, 미구현)
│   │   │   ├── news.py             # Naver (KR) + yfinance + NewsAPI (US)
│   │   │   ├── scraper.py          # trafilatura 기반 기사 본문 스크래핑
│   │   │   ├── disclosure.py       # DART 공시 API
│   │   │   └── exchange_rate.py    # open.er-api.com
│   │   ├── services/llm/           # LLM 분석 파이프라인
│   │   │   ├── adapter.py          # LLMAdapter ABC + Azure/OpenAI 구현
│   │   │   ├── analyzer.py         # 뉴스/공시 → LLM → 키워드 생성
│   │   │   └── prompts.py          # 프롬프트 템플릿
│   │   ├── models/                 # SQLAlchemy ORM
│   │   ├── schemas/stock.py        # Pydantic response 모델 (13개)
│   │   ├── dependencies.py         # get_stock_or_404
│   │   ├── scheduler.py            # AsyncIOScheduler (8am/6pm KST)
│   │   ├── config.py               # pydantic-settings (.env)
│   │   ├── database.py             # 엔진 + 세션 팩토리
│   │   └── main.py                 # FastAPI 앱 진입점
│   ├── alembic/                    # DB 마이그레이션 (4개)
│   ├── scripts/seed.py             # 초기 데이터
│   ├── tests/                      # pytest (120+ tests)
│   └── pyproject.toml              # uv 패키지 관리
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router
│   │   ├── components/
│   │   │   ├── layout/top-nav.tsx  # 네비 + 로그인 + 전체 동기화
│   │   │   ├── search/stock-search.tsx # Ctrl+K 종목 검색
│   │   │   ├── stock/              # 차트, 키워드, AI피드백, 동기화
│   │   │   └── ui/                 # shadcn/ui + toast
│   │   ├── services/
│   │   │   ├── api.ts              # 백엔드 API 클라이언트
│   │   │   └── auth.ts             # JWT 토큰 관리
│   │   └── types/stock.ts          # TypeScript 타입
│   └── package.json
├── docs/                           # 문서
├── CLAUDE.md                       # 프로젝트 가이드
└── TODOS.md                        # 할 일 목록
```

## 데이터 흐름

```
┌─────────────────────────────────────────────────┐
│              스케줄러 (8am/6pm KST)               │
│              또는 Admin 수동 동기화                │
└────────────────────┬────────────────────────────┘
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
┌────────┐    ┌──────────┐    ┌───────────┐
│Collector│    │Collector │    │ Collector  │
│주가/재무│    │뉴스(KR+US)│    │공시/환율   │
└────┬───┘    └─────┬────┘    └─────┬─────┘
     │              │               │
     └──────────────┼───────────────┘
                    ▼
              ┌──────────┐
              │PostgreSQL │
              └─────┬────┘
                    │
              ┌─────┴────┐
              │LLM 분석   │  최근 7일 뉴스/공시 조회
              │(Azure AI) │  → 키워드 자동 생성
              └─────┬────┘
                    │
              ┌─────┴────┐
              │ FastAPI   │  REST API + JWT 인증
              └─────┬────┘
                    │
              ┌─────┴────┐
              │ Next.js   │  대시보드 UI
              └──────────┘
```

## DB 테이블

| 테이블 | 설명 | 주요 제약 |
|--------|------|-----------|
| stocks | 종목 마스터 | ticker UNIQUE |
| price_history | 일별 OHLCV | (stock_id, date) UNIQUE |
| analyses | LLM 분석 결과 | (stock_id, date, period_type) UNIQUE |
| keyword_details | 키워드 상세 | analysis_id FK, cascade delete |
| daily_keywords | 일별 키워드 | analysis_id FK, cascade delete |
| financials | 재무지표 | (stock_id, period) UNIQUE |
| news | 뉴스 | (stock_id, url) UNIQUE |
| disclosures | 공시 | (stock_id, title, disclosed_at) UNIQUE |
| exchange_rates | 환율 | (date, currency_pair) UNIQUE |
| favorites | 즐겨찾기 | (user_id, stock_id) UNIQUE |

## API 엔드포인트

### 인증
- `POST /api/auth/login` — JWT 토큰 발급
- `GET /api/auth/me` — 현재 사용자 정보

### 주식 데이터
- `GET /api/stocks/search?q=` — 종목 검색 (DB + 외부 API)
- `GET /api/stocks/{ticker}` — 종목 상세 (없으면 자동 등록)
- `GET /api/stocks/{ticker}/prices?days=N` — 가격 히스토리
- `GET /api/stocks/{ticker}/analysis?period=daily` — LLM 키워드 분석
- `GET /api/stocks/{ticker}/news` — 뉴스 목록
- `GET /api/stocks/{ticker}/disclosures` — 공시 목록

### 즐겨찾기 (user_id 기반)
- `GET /api/favorites` — 목록
- `POST /api/favorites/{ticker}` — 추가
- `DELETE /api/favorites/{ticker}` — 삭제

### 관리자 (JWT admin 필수)
- `POST /api/admin/sync/stock/{ticker}` — 종목별 수집 + LLM 분석
- `POST /api/admin/sync/global` — 환율 수집
- `POST /api/admin/sync/all` — 전체 (즐겨찾기 종목 + 환율 + LLM)

### 환율
- `GET /api/exchange-rates/latest` — 최신 환율

## 환경변수 (.env.example 참조)

| 변수 | 필수 | 용도 |
|------|------|------|
| DATABASE_URL | 필수 | PostgreSQL 연결 |
| ADMIN_EMAIL, ADMIN_PASSWORD | 필수 | 관리자 로그인 |
| JWT_SECRET | 필수 | JWT 서명 |
| LLM_ENDPOINT, LLM_API_KEY, LLM_DEPLOYMENT | 선택 | LLM 분석 |
| NAVER_CLIENT_ID, NAVER_CLIENT_SECRET | 선택 | KR 뉴스 |
| NEWSAPI_KEY | 선택 | US 뉴스 |
| DART_API_KEY | 선택 | KR 공시 |
| SCHEDULER_ENABLED | 선택 | 자동 동기화 on/off |
