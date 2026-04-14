# Integrations

외부 서비스 연동 현황. 각 서비스별 상태, 용도, 인증 방식, 제한사항 정리.

---

## 연동 완료 (키 불필요)

### yfinance (US 주가 + 재무 + 뉴스)

| 항목 | 내용 |
|------|------|
| 용도 | US 종목 주가 (OHLCV), 재무지표, 뉴스 (10건), 종목 검색/자동등록 |
| Collector | `stock_price.py`, `financials.py`, `news.py`, `stock_lookup.py` |
| 인증 | 불필요 (무료) |
| 주의사항 | MultiIndex 컬럼 → `droplevel("Ticker")`. rate limit 있음. 뉴스는 최대 10건. 한국 종목은 `.KS`/`.KQ` 접미사 필요. |
| market 정규화 | exchange 코드 (NMS, NGM 등) → NASDAQ/NYSE/KRX 자동 변환 |

### FinanceDataReader (KR 주가 + 종목 검색)

| 항목 | 내용 |
|------|------|
| 용도 | KR 종목 주가 (OHLCV), KRX 전체 종목 검색 |
| Collector | `stock_price.py`, `stock_lookup.py` |
| 인증 | 불필요 (무료) |
| 주의사항 | KRX 종목코드 6자리. `asyncio.to_thread`로 비동기 래핑. |

### ExchangeRate API (환율)

| 항목 | 내용 |
|------|------|
| 용도 | 주요 통화 환율 (USD/KRW, USD/EUR, USD/JPY) |
| Collector | `exchange_rate.py` |
| 엔드포인트 | `https://open.er-api.com/v6/latest/USD` |
| 인증 | 불필요 (무료, 일 1,500회) |

---

## 연동 완료 (API 키 필요)

### Azure AI Foundry — LLM 분석 ✅

| 항목 | 내용 |
|------|------|
| 용도 | 뉴스/공시 → 키워드 자동 추출, AI 요약/피드백 생성 |
| Adapter | `app/services/llm/adapter.py` (AzureOpenAIAdapter) |
| API 형식 | Responses API (`input[]` → `output[].content[].text`) |
| 인증 | `LLM_ENDPOINT`, `LLM_API_KEY`, `LLM_DEPLOYMENT` (.env) |
| 인증 헤더 | `api-key` 헤더 |
| 현재 모델 | gpt-5.4-mini |
| 비용 | 종목당 1회 호출, 월 $2-5 예상 |
| 키 미설정 시 | LLM 분석 스킵, 나머지 동기화는 정상 진행 |

### Naver News API (KR 뉴스) ✅

| 항목 | 내용 |
|------|------|
| 용도 | KR 종목 관련 뉴스 수집 (50건/종목) |
| Collector | `news.py` (`_sync_naver_news`) |
| 인증 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` |
| 발급 | [Naver Developers](https://developers.naver.com/) → 애플리케이션 등록 → 검색 API |
| 제한 | 일 25,000회 |

### NewsAPI.org (US 뉴스) ✅

| 항목 | 내용 |
|------|------|
| 용도 | US 종목 영문 뉴스 수집 (30건/종목, yfinance 보조) |
| Collector | `news.py` (`_sync_newsapi`) |
| 인증 | `NEWSAPI_KEY` |
| 발급 | [NewsAPI.org](https://newsapi.org/register) → 가입 즉시 발급 |
| 제한 | 무료 플랜 일 100건 호출 |
| 키 미설정 시 | US 뉴스는 yfinance 10건만 수집 |

### DART 공시 API (KR 공시)

| 항목 | 내용 |
|------|------|
| 용도 | KR 종목 공시 목록 수집 |
| Collector | `disclosure.py` |
| 인증 | `DART_API_KEY` |
| 발급 | [DART OpenAPI](https://opendart.fss.or.kr/) → 회원가입 → 인증키 발급 |
| 제한 | 일 10,000회 |
| 현재 상태 | 코드 완성, **API 키 미설정** |

---

## 미연동 (TODO)

| 서비스 | 용도 | Phase |
|--------|------|-------|
| DART 재무제표 API | KR 재무지표 파싱 | 3 |
| 한국투자증권 OpenAPI | 실시간 호가/체결 (WebSocket) | 인프라 |
| YouTube Data API | 주식 유튜브 의견 수집 | 3 |

---

## 환경변수 요약

| 변수 | 필수 | 용도 | 발급처 |
|------|------|------|--------|
| `DATABASE_URL` | **필수** | PostgreSQL 연결 | 직접 설정 |
| `ADMIN_EMAIL` | **필수** | 관리자 로그인 | 직접 설정 |
| `ADMIN_PASSWORD` | **필수** | 관리자 비밀번호 | 직접 설정 |
| `JWT_SECRET` | **필수** | JWT 서명 | 직접 설정 |
| `LLM_ENDPOINT` | 선택 | Azure AI Foundry | Azure Portal |
| `LLM_API_KEY` | 선택 | LLM 인증 | Azure Portal |
| `LLM_DEPLOYMENT` | 선택 | 모델 배포명 | Azure Portal |
| `NAVER_CLIENT_ID` | 선택 | KR 뉴스 | [Naver Developers](https://developers.naver.com/) |
| `NAVER_CLIENT_SECRET` | 선택 | KR 뉴스 | 상동 |
| `NEWSAPI_KEY` | 선택 | US 뉴스 | [NewsAPI.org](https://newsapi.org/) |
| `DART_API_KEY` | 선택 | KR 공시 | [DART OpenAPI](https://opendart.fss.or.kr/) |
| `SCHEDULER_ENABLED` | 선택 | 자동 동기화 | `true`/`false` |

> 선택 항목 미설정 시 해당 기능만 스킵, 앱 정상 동작
