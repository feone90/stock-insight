# StockInsight — 주식 분석 대시보드 설계 문서

## 프로젝트 개요

주식 종목의 상승/하락/보합 요인을 한눈에 확인하고, AI 기반 피드백과 대책을 받을 수 있는 웹 서비스.

### 사용자
- 3명 (본인, 아내, 장인어른) — 중장기 투자자
- 인증 시스템은 추후 구현 (TODO)

### 핵심 목표
1. 종목 즐겨찾기 관리
2. 기간별(일간/주간/월간/분기/반기/연간) 종목 분석
3. 상승/하락/보합 원인을 키워드로 한눈에 파악
4. 키워드 클릭 시 상세 리포트 (출처, 영향도 포함)
5. AI 기반 종합 피드백 및 대책 제안
6. 일봉 차트에서 특정 날짜 클릭 → 그날의 원인 분석 (매일 공부용)

### 타겟 시장
- 한국 (코스피/코스닥) + 미국 (NYSE/NASDAQ)

### 언어
- 한국어 전용

---

## 아키텍처

### 방식: 모노리포 풀스택 (Next.js + FastAPI + PostgreSQL)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   프론트엔드      │     │   백엔드 API      │     │   데이터 저장소    │
│   Next.js        │ ──→ │   FastAPI        │ ──→ │   PostgreSQL    │
│   (React)        │     │   (Python)       │     │                 │
│                  │     │                  │     │   - 종목 마스터    │
│   - 대시보드 UI   │     │   - REST API     │     │   - 주가 히스토리  │
│   - 캔들+라인차트  │     │   - 데이터 수집    │     │   - 분석 결과 캐시 │
│   - 키워드 드릴다운│     │   - LLM 어댑터    │     │   - 즐겨찾기      │
│                  │     │   - 분석 엔진     │     │                 │
│   배포: Vercel   │     │   배포: AWS/Azure │     │   로컬→클라우드   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │         │
                    ┌─────────┘         └─────────┐
                    ▼                             ▼
          ┌─────────────────┐           ┌─────────────────┐
          │   외부 데이터 소스  │           │   LLM 서비스      │
          │                  │           │                  │
          │   - KRX          │           │   어댑터 패턴      │
          │   - Yahoo Finance│           │   - Claude API   │
          │   - DART (공시)   │           │   - OpenAI GPT   │
          │   - 뉴스 API     │           │   - Azure OpenAI │
          │   - 환율 API     │           │   - (확장 가능)    │
          └─────────────────┘           └─────────────────┘

          ┌─────────────────┐
          │   스케줄러        │
          │   APScheduler    │
          │                  │
          │   - 일간 주가 수집 │
          │   - 정기 분석 생성 │
          │   - 뉴스/공시 수집 │
          │   - 환율 업데이트  │
          └─────────────────┘
```

### 데이터 흐름
1. 스케줄러가 외부 API에서 데이터 수집 → DB 저장
2. 사용자가 종목 선택 → FastAPI가 DB에서 데이터 조회
3. LLM에 데이터 전달 → 상승/하락 원인 분석 + 키워드 생성
4. 분석 결과 DB 캐시 → 프론트엔드 대시보드에 표시

---

## 대시보드 UI

### 레이아웃 구조

```
┌──────────────────────────────────────────────────────┐
│  🔍 종목 검색                           ⭐ 즐겨찾기  │
├──────────────────────────────────────────────────────┤
│  삼성전자 005930 코스피 ⭐       71,500원 ▼1,200(-1.65%)│
│  [일간] [주간] [월간] [분기] [반기] [연간]              │
├────────────────────────────────┬─────────────────────┤
│                                │                     │
│  📈 캔들 + 라인 차트             │  📋 상세 리포트      │
│  (종가라인/MA5/MA20/MA60 토글)   │                     │
│                                │  ← 키워드 클릭 시    │
│  ────────────────────────      │     상세 내용 표시   │
│  4/1    4/2    4/3    4/4      │                     │
│  실적호조 HBM수주 관세발표 반등매수 │  - 상세 설명        │
│  (키워드 타임라인)               │  - 출처             │
│                                │  - 영향도/지속성     │
├────────────────────────────────┤                     │
│  📈 상승요인    📉 하락요인       │─────────────────────│
│  [HBM수주] [AI수요↑]  [환율↑]   │  주요 지표          │
│                                │  시가총액: 426.7조   │
│  ➡️ 보합요인                    │  PER: 12.3배       │
│  [실적부합] [배당유지]           │  PBR: 1.2배        │
├────────────────────────────────┤  배당수익률: 2.1%    │
│  🤖 AI 피드백 & 대책             │  52주 최고/최저     │
│  종합 분석 + 투자 전략 제안       │                     │
└────────────────────────────────┴─────────────────────┘
```

### 차트 기능
- **캔들스틱(일봉)** 기본 표시
- **오버레이 토글**: 종가 라인 / MA5 / MA20 / MA60 — ON/OFF 가능
- **호버 툴팁**: 봉에 마우스 올리면 해당 날짜의 등락률 + 대표 키워드 1~2개
- **차트 아래 키워드 타임라인**: 날짜별 대표 키워드 태그 (색상 구분)
- **봉 또는 키워드 클릭**: 오른쪽 상세 리포트 패널에 내용 표시
- 차트 라이브러리: Lightweight Charts (TradingView 오픈소스) 또는 Recharts

### 키워드 시스템
- **상승 요인**: 초록색 태그
- **하락 요인**: 빨간색 태그
- **보합 요인**: 회색 태그
- 각 키워드에 포함: 상세 설명, 출처(뉴스/공시 등), 영향도(높음/중간/낮음), 지속성(단기/중기/장기)

### AI 피드백
- LLM이 수집된 데이터를 종합 분석한 요약문
- 중장기 투자자 관점의 대책/전략 제안
- 추후 대화형 질문 기능 확장 가능하도록 설계

---

## 데이터 모델

```sql
-- 종목 마스터
stocks (
  id, ticker, name, market,  -- market: KRX, NYSE, NASDAQ
  sector, created_at
)

-- 주가 히스토리 (일별)
price_history (
  id, stock_id, date,
  open, high, low, close, volume
)

-- 분석 결과 (LLM 생성 → 캐시)
analyses (
  id, stock_id, date,
  period_type,  -- daily, weekly, monthly, quarterly, semi_annual, annual
  summary, feedback,
  created_at
)

-- 키워드 상세
keyword_details (
  id, analysis_id,
  keyword, type,  -- bullish, bearish, neutral
  detail, source,
  impact_level, duration,  -- impact: high/mid/low, duration: short/mid/long
  created_at
)

-- 뉴스
news (
  id, stock_id,
  title, content, source, url,
  published_at
)

-- 공시 (DART)
disclosures (
  id, stock_id,
  title, content, type,
  disclosed_at
)

-- 재무제표
financials (
  id, stock_id, period, period_type,
  revenue, operating_profit, net_income,
  per, pbr, roe, dividend_yield
)

-- 즐겨찾기
favorites (
  id, user_id, stock_id, created_at
)

-- 환율
exchange_rates (
  id, date, currency_pair, rate  -- e.g. USD/KRW
)

-- 시장 지표
market_indices (
  id, date, index_name, value, change, change_percent
)

-- Phase 2: 유튜브 채널
youtube_channels (
  id, channel_id, name, stock_id
)

-- Phase 2: 유튜브 의견
youtube_opinions (
  id, channel_id, stock_id,
  video_id, title, summary,
  published_at
)
```

---

## API 엔드포인트

```
종목
  GET  /api/stocks/search?q={query}           — 종목 검색
  GET  /api/stocks/{ticker}                   — 종목 상세 정보

주가
  GET  /api/stocks/{ticker}/prices?period={period}  — 기간별 주가 데이터

분석
  GET  /api/stocks/{ticker}/analysis?period={period}&date={date}
       — 해당 기간 종합 분석 (키워드 + 피드백)
  GET  /api/stocks/{ticker}/analysis/daily/{date}
       — 특정 날짜 키워드 + 상세 리포트

즐겨찾기
  GET    /api/favorites                       — 즐겨찾기 목록
  POST   /api/favorites/{ticker}              — 추가
  DELETE /api/favorites/{ticker}              — 제거

LLM (내부용)
  POST  /api/internal/analyze                 — 데이터 → LLM 분석 요청
```

MVP 단계에서는 모든 API가 **목업 JSON을 반환**하고, 이후 실제 데이터/LLM으로 교체.

---

## LLM 어댑터 레이어

```python
# 어댑터 패턴 — 키(API Key) 설정만으로 모델 교체 가능
LLMAdapter
├── ClaudeAdapter      (Anthropic Claude API)
├── OpenAIAdapter      (OpenAI GPT API)
├── AzureOpenAIAdapter (Azure OpenAI)
└── (확장 가능)

# 각 어댑터는 동일한 인터페이스 구현:
analyze(stock_data, period, context) → AnalysisResult
```

최적 모델 추천:
- **분석 품질 우선**: Claude (긴 컨텍스트에 강점, 한국어 분석 우수)
- **비용 효율 우선**: GPT-4o-mini (저렴하면서 준수한 품질)
- **추천 전략**: Claude로 시작, 비용 부담 시 GPT-4o-mini로 전환 가능한 구조

---

## 데이터 소스 및 Phase 계획

### Phase 1 — MVP (목업 데이터 → 실제 연동)
| 데이터 | 소스 | 비용 |
|--------|------|------|
| 한국 주가 | FinanceDataReader / KRX API | 무료 |
| 미국 주가 | yfinance (Yahoo Finance) | 무료 |
| 재무제표 | DART OpenAPI / yfinance | 무료 |
| 뉴스 | 네이버 뉴스 검색 API / NewsAPI | 무료 |
| 환율 | 한국은행 API / ExchangeRate API | 무료 |
| 공시 | DART OpenAPI | 무료 |

### Phase 2 — 분석 깊이 강화
| 데이터 | 소스 |
|--------|------|
| 섹터/업종 동향 | KRX 업종별 지수 |
| 기관/외국인 매매 동향 | KRX 투자자별 매매 |
| 금리/채권 시장 | 한국은행 API |
| 배당 정보 | DART / yfinance |
| 유튜브 채널 의견 | YouTube Data API v3 + youtube-transcript-api |

### Phase 3 — 고급 분석
| 데이터 | 소스 |
|--------|------|
| 국내/국제 정서 | Fear & Greed Index 등 |
| 원자재 가격 | yfinance (금, 유가 등) |
| 소셜 센티먼트 | 커뮤니티 크롤링 |
| 애널리스트 컨센서스 | 증권사 리포트 |
| 회사 홈페이지 | 웹 크롤링 |

---

## 프로젝트 구조

```
cw-cy-stock/
├── frontend/                  # Next.js (React)
│   ├── src/
│   │   ├── app/               # Next.js App Router
│   │   ├── components/
│   │   │   ├── chart/         # 캔들+라인 차트
│   │   │   ├── dashboard/     # 대시보드 레이아웃
│   │   │   ├── keywords/      # 상승/하락/보합 키워드 태그
│   │   │   └── common/        # 공통 (검색, 네비게이션)
│   │   ├── hooks/             # 커스텀 훅
│   │   ├── services/          # API 호출 레이어
│   │   ├── types/             # TypeScript 타입
│   │   └── mocks/             # 목업 데이터
│   └── package.json
│
├── backend/                   # FastAPI (Python)
│   ├── app/
│   │   ├── api/               # 라우터 (엔드포인트)
│   │   ├── models/            # DB 모델 (SQLAlchemy)
│   │   ├── schemas/           # Pydantic 스키마
│   │   ├── services/
│   │   │   ├── llm/           # LLM 어댑터 레이어
│   │   │   ├── data_collector/ # 데이터 수집 모듈
│   │   │   └── analyzer/      # 분석 엔진
│   │   ├── mocks/             # 목업 데이터
│   │   └── config.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── docs/                      # 설계 문서
└── docker-compose.yml         # 로컬 개발용
```

---

## TODO (추후 구현)

- [ ] 인증 시스템 (사용자별 즐겨찾기 분리)
- [ ] 실시간 데이터 (WebSocket, 장중 자동 갱신)
- [ ] 대화형 AI 질문 기능 (챗 인터페이스)
- [ ] K8s 컨테이너 기반 백엔드 배포 (AWS/Azure)
- [ ] 유튜브 채널 의견 수집 (Phase 2)
- [ ] 다국어 지원 (영어)

---

## 기술 스택 요약

| 영역 | 기술 |
|------|------|
| 프론트엔드 | Next.js, React, TypeScript |
| UI 프레임워크 | shadcn/ui + Tailwind CSS (다크 테마 기본) |
| 차트 | Lightweight Charts 또는 Recharts |
| 백엔드 | FastAPI, Python |
| DB | PostgreSQL (MVP는 목업 데이터) |
| LLM | Claude API (추천) / OpenAI / Azure (어댑터 패턴) |
| 배포 (프론트) | Vercel |
| 배포 (백엔드) | 로컬 → AWS/Azure (K8s) |
| 스케줄러 | APScheduler |
| 컨테이너 | Docker, docker-compose |

---

## 프론트엔드 공통 컴포넌트

shadcn/ui + Tailwind CSS 기반, 다크 테마 기본. 컴포넌트를 프로젝트에 복사하여 소유권 100%.

### 공통 컴포넌트 목록
| 컴포넌트 | 용도 |
|----------|------|
| Button | Primary, Secondary, 매수(green), 매도(red), Link |
| Card | 지표 카드 (시가총액, PER 등) |
| Badge/Tag | 상승(green)/하락(red)/보합(gray) 키워드 태그 |
| Tabs | 기간 선택 (일간~연간) |
| Search (⌘K) | Command Palette 스타일 종목 검색 |
| Toggle | 차트 오버레이 ON/OFF (종가라인, MA5/20/60) |
| Tooltip | 차트 봉 호버 시 키워드 표시 |
| Panel | 오른쪽 상세 리포트 패널 |

### 디자인 원칙
- 다크 테마 기본 (배경: slate-900/950, 텍스트: slate-50)
- 상승=green, 하락=red, 보합=gray 색상 일관 적용
- 라운딩: 8px (카드), 20px (태그/뱃지), 6px (버튼)
- 컴포넌트 간 간격: Tailwind spacing 시스템 (4px 단위)
