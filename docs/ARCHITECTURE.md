# StockInsight - 프로젝트 구조

부부 + 장인어른이 함께 쓸 주식 분석 대시보드.

## 기술 스택

| 계층 | 기술 |
|------|------|
| 프론트엔드 | Next.js 15, React 19, Tailwind CSS, shadcn/ui, lightweight-charts v5 |
| 백엔드 | FastAPI, SQLAlchemy (async), Alembic |
| DB | PostgreSQL (asyncpg) |
| 데이터 수집 | yfinance (US), FinanceDataReader (KR), Naver News API, DART API, ExchangeRate API |
| 인프라 | Docker Compose |

## 디렉토리 구조

```
cw-cy-stock/
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI 라우터
│   │   │   ├── admin.py          # POST /api/admin/sync/* (동기화)
│   │   │   ├── analysis.py       # GET /api/stocks/{ticker}/analysis
│   │   │   ├── exchange_rates.py # GET /api/exchange-rates/latest
│   │   │   ├── favorites.py      # GET/POST/DELETE /api/favorites
│   │   │   └── stocks.py         # GET /api/stocks/* (검색, 상세, 가격, 뉴스, 공시)
│   │   ├── collectors/           # 외부 데이터 수집 모듈
│   │   │   ├── stock_price.py    # yfinance / FinanceDataReader
│   │   │   ├── financials.py     # yfinance (US) / DART (KR, 미구현)
│   │   │   ├── news.py           # Naver News API
│   │   │   ├── disclosure.py     # DART 공시 API
│   │   │   └── exchange_rate.py  # open.er-api.com
│   │   ├── models/               # SQLAlchemy ORM 모델
│   │   │   ├── stock.py          # 종목 마스터
│   │   │   ├── price.py          # 일별 가격 (OHLCV)
│   │   │   ├── analysis.py       # 분석 결과 + 키워드
│   │   │   ├── financial.py      # 재무지표 (PER, PBR, ROE 등)
│   │   │   ├── news.py           # 뉴스
│   │   │   ├── disclosure.py     # 공시
│   │   │   ├── exchange_rate.py  # 환율
│   │   │   └── favorite.py       # 즐겨찾기
│   │   ├── mocks/                # Seed 전용 목업 데이터 (레거시)
│   │   ├── config.py             # pydantic-settings 환경변수
│   │   ├── database.py           # 엔진 + 세션 팩토리
│   │   └── main.py               # FastAPI 앱 진입점
│   ├── alembic/                  # DB 마이그레이션
│   ├── scripts/seed.py           # 초기 데이터 시드
│   ├── tests/                    # pytest (69개, 커버리지 98.5%)
│   │   ├── conftest.py           # DB/Client 픽스처
│   │   ├── test_api.py           # API 엔드포인트 테스트
│   │   ├── test_admin_api.py     # Admin sync API 테스트
│   │   └── test_collectors.py    # Collector 단위 테스트
│   ├── pyproject.toml            # pytest + coverage 설정
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx        # 루트 레이아웃 (TopNav)
│   │   │   ├── page.tsx          # 홈 (즐겨찾기 목록)
│   │   │   └── stock/[ticker]/
│   │   │       └── page.tsx      # 종목 대시보드 (차트+키워드+AI)
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   └── top-nav.tsx   # 상단 네비게이션 + 전체 동기화
│   │   │   ├── search/
│   │   │   │   └── stock-search.tsx # ⌘K 종목 검색 다이얼로그
│   │   │   ├── stock/            # 대시보드 구성요소
│   │   │   │   ├── price-chart.tsx      # 캔들+라인 차트
│   │   │   │   ├── chart-toggles.tsx    # MA/종가 토글
│   │   │   │   ├── period-tabs.tsx      # 기간 탭 (일간~연간)
│   │   │   │   ├── keyword-timeline.tsx # 일별 키워드 타임라인
│   │   │   │   ├── keyword-section.tsx  # 키워드 카드 목록
│   │   │   │   ├── keyword-tag.tsx      # 상승/하락/보합 태그
│   │   │   │   ├── detail-panel.tsx     # 키워드 상세 리포트
│   │   │   │   ├── ai-feedback.tsx      # AI 요약+피드백 패널
│   │   │   │   ├── stats-card.tsx       # 재무지표 카드
│   │   │   │   └── stock-header.tsx     # 종목명+가격+동기화 버튼
│   │   │   └── ui/               # shadcn/ui 기반 공통 UI
│   │   ├── services/api.ts       # 백엔드 API 클라이언트
│   │   ├── types/stock.ts        # TypeScript 타입 정의
│   │   └── lib/utils.ts          # cn() 유틸
│   └── package.json
└── docker-compose.yml            # PostgreSQL 서비스
```

## 데이터 흐름

```
[외부 API] → [Collector] → [PostgreSQL] → [FastAPI] → [Next.js]

1. 사용자가 "동기화" 버튼 클릭
2. POST /api/admin/sync/stock/{ticker}
3. 각 Collector가 외부 API 호출 → DB upsert
4. 프론트엔드가 GET 엔드포인트로 최신 데이터 조회

* 가격 데이터는 on-demand: GET /prices?days=N 요청 시
  DB에 해당 기간 데이터 부족하면 자동 수집 후 반환
```

## DB 테이블

| 테이블 | 설명 | 주요 제약 |
|--------|------|-----------|
| stocks | 종목 마스터 | ticker UNIQUE |
| price_history | 일별 OHLCV | (stock_id, date) UNIQUE |
| analyses | 분석 결과 | stock_id FK |
| keyword_details | 키워드 상세 | analysis_id FK |
| daily_keywords | 일별 키워드 | analysis_id FK |
| financials | 재무지표 | (stock_id, period) UNIQUE |
| news | 뉴스 | (stock_id, url) UNIQUE |
| disclosures | 공시 | (stock_id, title, disclosed_at) UNIQUE |
| exchange_rates | 환율 | (date, currency_pair) UNIQUE |
| favorites | 즐겨찾기 | stock_id UNIQUE |

## API 엔드포인트

### 주식 데이터
- `GET /api/stocks/search?q=` — 종목 검색
- `GET /api/stocks/{ticker}` — 종목 상세 (재무지표 포함)
- `GET /api/stocks/{ticker}/prices?days=N` — 가격 (on-demand 자동 수집)
- `GET /api/stocks/{ticker}/analysis?period=` — 키워드 분석
- `GET /api/stocks/{ticker}/news` — 뉴스 목록
- `GET /api/stocks/{ticker}/disclosures` — 공시 목록

### 즐겨찾기
- `GET /api/favorites` — 즐겨찾기 목록
- `POST /api/favorites/{ticker}` — 추가
- `DELETE /api/favorites/{ticker}` — 삭제

### 환율
- `GET /api/exchange-rates/latest` — 최신 환율

### 관리자 (동기화)
- `POST /api/admin/sync/stock/{ticker}` — 종목별 수집
- `POST /api/admin/sync/global` — 환율 수집
- `POST /api/admin/sync/all` — 전체 (즐겨찾기 종목 + 환율)

## 실행 방법

```bash
# DB 시작
docker-compose up -d

# 백엔드
cd backend
source venv/bin/activate
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload --port 8000

# 프론트엔드
cd frontend
npm install
npm run dev

# 테스트
cd backend
source venv/bin/activate
python -m pytest tests/ -v --cov=app
```

## 환경변수

### backend/.env
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/stockinsight
DART_API_KEY=       # 공시/재무 수집 (KR)
NAVER_CLIENT_ID=    # 뉴스 수집
NAVER_CLIENT_SECRET=
```

### frontend/.env.local
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 현재 상태 (2026-04-09)

### 완료
- 프론트엔드 대시보드 (차트, 키워드, 즐겨찾기, 검색)
- PostgreSQL 연동 (10개 테이블, Alembic 마이그레이션)
- 5개 Collector (주가, 재무, 뉴스, 공시, 환율)
- 수동 동기화 (종목별 + 전체)
- 기간별 차트 (일간~연간, on-demand 자동 수집)
- 백엔드 테스트 69개, 커버리지 98.5%

### TODO
- LLM 어댑터 연동 (뉴스/공시 → 키워드 자동 생성)
- KR 재무지표 DART 파싱
- 인증 시스템
- 실시간 데이터 (WebSocket)
- 대화형 AI 질문 기능
- K8s 기반 배포
