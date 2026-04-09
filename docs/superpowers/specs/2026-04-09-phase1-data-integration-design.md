# Phase 1 실제 데이터 연동 설계

## 개요

StockInsight에 실제 외부 데이터 소스를 연동한다. 스케줄러 대신 **수동 동기화 버튼**으로 데이터를 수집하며, 종목별/글로벌 단위로 동기화를 수행한다.

### 데이터 소스

| 데이터 | 소스 | API 키 필요 | 대상 |
|--------|------|-------------|------|
| 한국 주가 | FinanceDataReader | 불필요 | KR 종목 |
| 미국 주가 | yfinance | 불필요 | US 종목 |
| 재무지표 | yfinance (US) / DART (KR) | DART만 필요 | 종목별 |
| 뉴스 | Naver News API | 필요 (Client ID/Secret) | KR 종목명 검색 |
| 공시 | DART OpenAPI | 필요 (API Key) | KR 종목 |
| 환율 | ExchangeRate API (exchangerate-api.com) | 불필요 | 글로벌 |

> **Phase 1 범위**: 종목명으로 직접 검색한 뉴스만 수집. CNN/매크로 뉴스 + LLM 기반 연관성 태깅은 Phase 2로 이관.

---

## 아키텍처

### 접근: Flat Collector 모듈 (Option A)

각 데이터 소스별 독립 collector 모듈. Admin API 라우터가 직접 collector를 호출. 서비스 레이어나 태스크 큐 없이 단순하게 구현.

```
Frontend (동기화 버튼)
  ↓ POST /api/admin/sync/...
Backend Admin API Router
  ↓ 직접 호출
Collector 모듈 (5개)
  ↓ httpx / 라이브러리
외부 API → DB 저장
```

---

## 새 DB 테이블 (4개)

### news

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | int PK | |
| stock_id | int FK(stocks.id) | 관련 종목 |
| title | varchar(500) | 뉴스 제목 |
| source | varchar(100) | 출처 (예: 네이버뉴스) |
| url | varchar(1000) | 원문 링크 |
| published_at | datetime | 기사 발행일 |
| created_at | datetime | 수집 시각 |

UniqueConstraint: (stock_id, url) — 중복 뉴스 방지

### disclosures

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | int PK | |
| stock_id | int FK(stocks.id) | 관련 종목 |
| title | varchar(500) | 공시 제목 |
| content | text | 공시 내용 (요약) |
| disclosure_type | varchar(50) | 공시 유형 |
| disclosed_at | datetime | 공시일 |
| created_at | datetime | 수집 시각 |

UniqueConstraint: (stock_id, title, disclosed_at) — 중복 공시 방지

### financials

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | int PK | |
| stock_id | int FK(stocks.id) | 관련 종목 |
| period | varchar(20) | 기간 (예: "2025Q4") |
| period_type | varchar(20) | quarterly / annual |
| revenue | bigint nullable | 매출액 |
| operating_profit | bigint nullable | 영업이익 |
| net_income | bigint nullable | 순이익 |
| per | float nullable | PER |
| pbr | float nullable | PBR |
| roe | float nullable | ROE |
| dividend_yield | float nullable | 배당수익률 |
| market_cap | bigint nullable | 시가총액 |
| created_at | datetime | 수집 시각 |

UniqueConstraint: (stock_id, period) — 동일 기간 중복 방지

### exchange_rates

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | int PK | |
| date | date | 기준일 |
| currency_pair | varchar(10) | 예: "USD/KRW" |
| rate | float | 환율 |
| created_at | datetime | 수집 시각 |

UniqueConstraint: (date, currency_pair) — 동일 날짜/통화 중복 방지

---

## Collector 모듈 (5개)

```
backend/app/collectors/
├── __init__.py
├── stock_price.py      # 주가 수집
├── financials.py       # 재무지표 수집
├── news.py             # 뉴스 수집
├── disclosure.py       # 공시 수집
└── exchange_rate.py    # 환율 수집
```

### 공통 패턴

```python
async def sync_prices(db: AsyncSession, stock: Stock) -> dict:
    """주가 동기화. 반환: {"prices_synced": 90}"""
    # 1. stock.market으로 KR/US 판별
    # 2. KR → FinanceDataReader, US → yfinance
    # 3. 최근 1년 일봉 데이터 가져오기
    # 4. DB에 upsert (기존 데이터 있으면 스킵)
    # 5. Stock.current_price, change, change_percent 최신값으로 업데이트
    # 6. 결과 요약 반환
```

각 collector는:
- `AsyncSession`과 `Stock` 객체를 받음
- 외부 API 호출에 `httpx.AsyncClient` 사용 (yfinance/fdr은 동기 라이브러리이므로 `asyncio.to_thread`로 래핑)
- 에러 발생 시 예외를 raise하지 않고 에러 메시지를 반환 (다른 collector에 영향 없음)
- upsert 패턴: UniqueConstraint 기반 ON CONFLICT DO NOTHING 또는 merge

### stock_price.py

- **KR**: `FinanceDataReader.DataReader(ticker, start_date)` — 최근 1년
- **US**: `yfinance.download(ticker, period="1y")` — 최근 1년
- `price_history` 테이블에 bulk insert (중복은 스킵)
- `stocks` 테이블의 `current_price`, `change`, `change_percent`를 최신 종가로 업데이트

### financials.py

- **US**: `yfinance.Ticker(ticker).info` — PER, PBR, market_cap 등
- **KR**: DART OpenAPI `/api/fnlttSinglAcnt.json` — 재무제표 단일회사
- `financials` 테이블에 upsert

### news.py

- Naver News API: `https://openapi.naver.com/v1/search/news.json?query={종목명}`
- 최근 50건 수집
- `news` 테이블에 insert (URL 기준 중복 스킵)

### disclosure.py

- DART OpenAPI: `https://opendart.fss.or.kr/api/list.json?corp_code={code}`
- DART 고유번호(corp_code)는 Stock 모델에 `dart_code` 컬럼 추가하여 관리
- `disclosures` 테이블에 insert (제목+일자 기준 중복 스킵)
- **KR 종목만 해당** (US는 스킵)

### exchange_rate.py

- `https://open.er-api.com/v6/latest/USD` (무료, 키 불필요)
- USD/KRW, EUR/KRW, JPY/KRW 등 주요 통화쌍 수집
- `exchange_rates` 테이블에 upsert

---

## Stock 모델 변경

```python
# 기존 필드에 추가
dart_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

DART API 사용을 위해 한국 종목의 고유번호를 저장. disclosure collector가 `dart_code`가 비어있는 KR 종목을 만나면 DART 기업코드 API(`https://opendart.fss.or.kr/api/corpCode.xml`)에서 전체 코드를 다운로드하여 ticker 매칭 후 `dart_code`를 자동 설정. 한 번 설정되면 이후에는 재조회하지 않음.

---

## Admin API 엔드포인트

```
backend/app/api/admin.py
```

### POST /api/admin/sync/stock/{ticker}

해당 종목의 모든 데이터를 동기화:
1. 주가 (stock_price collector)
2. 재무지표 (financials collector)
3. 뉴스 (news collector)
4. 공시 (disclosure collector, KR만)

```json
// Response
{
  "status": "ok",
  "ticker": "005930",
  "synced": {
    "prices": 245,
    "financials": 4,
    "news": 42,
    "disclosures": 15
  },
  "errors": []
}
```

### POST /api/admin/sync/global

글로벌 데이터 동기화:
1. 환율 (exchange_rate collector)

```json
{
  "status": "ok",
  "synced": {
    "exchange_rates": 3
  },
  "errors": []
}
```

### POST /api/admin/sync/all

즐겨찾기 전체 종목 + 글로벌:
1. 즐겨찾기의 모든 종목에 대해 `/sync/stock/{ticker}` 순차 실행
2. `/sync/global` 실행

```json
{
  "status": "ok",
  "stocks_synced": ["005930", "AAPL", "TSLA"],
  "global_synced": true,
  "total_synced": {
    "prices": 735,
    "financials": 12,
    "news": 126,
    "disclosures": 30,
    "exchange_rates": 3
  },
  "errors": []
}
```

---

## 프론트엔드 동기화 UI

### 종목 대시보드 — "동기화" 버튼

- 위치: 종목 헤더 영역 (종목명 옆)
- 클릭 → `POST /api/admin/sync/stock/{ticker}`
- 동기화 중: 버튼에 스피너 + 비활성화
- 완료: 토스트 알림 ("삼성전자 동기화 완료: 주가 245건, 뉴스 42건...")
- 에러: 토스트 에러 ("뉴스 수집 실패: API 키 미설정")
- 완료 후 대시보드 데이터 자동 리프레시

### 네비게이션 — "전체 동기화" 버튼

- 위치: 상단 네비게이션 바 우측
- 클릭 → `POST /api/admin/sync/all`
- 동기화 중: 버튼에 스피너 + 비활성화
- 완료: 토스트 알림 (요약)
- 시간이 오래 걸릴 수 있음 → 사용자에게 기다리라는 안내

---

## 환경변수

```env
# backend/.env에 추가
DART_API_KEY=your_dart_api_key_here
NAVER_CLIENT_ID=your_naver_client_id_here
NAVER_CLIENT_SECRET=your_naver_client_secret_here
```

`backend/app/config.py`의 `Settings`에 추가:

```python
dart_api_key: str = ""
naver_client_id: str = ""
naver_client_secret: str = ""
```

키가 비어있으면 해당 collector는 스킵하고 errors에 "API key not configured" 포함.

---

## 새 Python 패키지

```
yfinance
FinanceDataReader
```

`requirements.txt`에 추가.

---

## 데이터 조회 API (신규)

수집된 뉴스/공시/환율을 확인할 수 있는 기본 조회 엔드포인트:

```
GET /api/stocks/{ticker}/news?limit=50        → 해당 종목 뉴스 목록 (최신순)
GET /api/stocks/{ticker}/disclosures?limit=30  → 해당 종목 공시 목록 (최신순)
GET /api/exchange-rates/latest                 → 최신 환율 목록
```

---

## 기존 API 연동

- `GET /api/stocks/{ticker}`: stats 섹션을 `financials` 테이블에서 조회하도록 변경 (현재 mock)
- `GET /api/stocks/{ticker}/prices`: 이미 DB 연동 완료 (변경 없음)
- 뉴스/공시 데이터는 Phase 1에서 수집만 하고, 대시보드 표시는 기존 analysis 키워드 시스템 유지. 추후 LLM 연동 시 뉴스/공시 → 키워드 자동 생성.

---

## 에러 처리 전략

- 각 collector는 독립적으로 실행. 하나가 실패해도 나머지는 계속 진행.
- 외부 API 타임아웃: httpx 기본 30초, yfinance/fdr은 asyncio.to_thread에 60초 제한
- API 키 미설정: 해당 collector 스킵, errors 배열에 메시지 추가
- 네트워크 에러: errors 배열에 추가, 다음 collector로 진행
- Response에 항상 errors 배열 포함 → 프론트에서 부분 실패 표시 가능

---

## Phase 1에서 하지 않는 것

- 스케줄러/크론 자동 수집
- CNN/해외 뉴스 크롤링
- LLM 기반 뉴스-종목 연관성 분석
- 뉴스/공시 → 키워드 자동 생성
- market_indices 테이블 (시장 지표)
- 미국 종목 뉴스 (Naver API는 한국 뉴스만)
- 미국 종목 공시 (DART는 한국만)
