# Integrations

외부 서비스 연동 현황. 각 서비스별 상태, 용도, 인증 방식, 제한사항 정리.

---

## 연동 완료

### yfinance (US 주가 + 재무)

| 항목 | 내용 |
|------|------|
| 용도 | US 종목 주가 (OHLCV), 재무지표 (PER, PBR, ROE, 시가총액 등) |
| Collector | `backend/app/collectors/stock_price.py`, `financials.py` |
| 인증 | 불필요 (무료) |
| 호출 방식 | `yf.download()` (주가), `yf.Ticker().info` (재무) |
| 주의사항 | MultiIndex 컬럼 반환 → `droplevel("Ticker")` 필요. rate limit 있음 (과도한 호출 시 차단). `asyncio.to_thread`로 비동기 래핑. |
| 데이터 범위 | 최대 수십 년치 가능, 현재 on-demand로 요청 기간만큼 수집 |

### FinanceDataReader (KR 주가)

| 항목 | 내용 |
|------|------|
| 용도 | KR 종목 주가 (OHLCV) |
| Collector | `backend/app/collectors/stock_price.py` |
| 인증 | 불필요 (무료) |
| 호출 방식 | `fdr.DataReader(ticker, start)` |
| 주의사항 | KRX 종목코드 6자리 (예: `005930`). `asyncio.to_thread`로 비동기 래핑. |
| 데이터 범위 | 수년치 가능 |

### ExchangeRate API (환율)

| 항목 | 내용 |
|------|------|
| 용도 | 주요 통화 환율 (USD/KRW, USD/EUR, USD/JPY) |
| Collector | `backend/app/collectors/exchange_rate.py` |
| 엔드포인트 | `https://open.er-api.com/v6/latest/USD` |
| 인증 | 불필요 (무료 tier) |
| 호출 방식 | httpx GET |
| 주의사항 | 무료 tier는 일 1,500회 제한. 하루 1회 동기화면 충분. |
| 수집 통화 | `CURRENCY_PAIRS` dict에서 관리 (`KRW`, `EUR`, `JPY`) |

---

## 연동 완료 (API 키 필요)

### Naver News API (뉴스)

| 항목 | 내용 |
|------|------|
| 용도 | 종목 관련 뉴스 수집 |
| Collector | `backend/app/collectors/news.py` |
| 엔드포인트 | `https://openapi.naver.com/v1/search/news.json` |
| 인증 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (backend/.env) |
| 발급 방법 | [Naver Developers](https://developers.naver.com/) → 애플리케이션 등록 → 검색 API 사용 |
| 호출 방식 | httpx GET, 헤더에 Client ID/Secret |
| 주의사항 | 일 25,000회 제한. HTML 태그 포함된 title → `strip_html()` 처리. pubDate RFC 2822 형식. |
| 키 미설정 시 | `{"news_synced": 0, "error": "Naver API 키 미설정"}` 반환 (예외 없음) |

### DART 공시 API (공시)

| 항목 | 내용 |
|------|------|
| 용도 | KR 종목 공시 목록 수집 |
| Collector | `backend/app/collectors/disclosure.py` |
| 엔드포인트 | `https://opendart.fss.or.kr/api/list.json` |
| 인증 | `DART_API_KEY` (backend/.env) |
| 발급 방법 | [DART OpenAPI](https://opendart.fss.or.kr/) → 회원가입 → 인증키 발급 |
| 호출 방식 | httpx GET, query param에 `crtfc_key` |
| 주의사항 | KR 종목만 해당. `stock.dart_code` (기업고유번호) 필요. 일 10,000회 제한. |
| 키/코드 미설정 시 | 에러 메시지와 함께 graceful 반환 |

---

## 미연동 (TODO)

### DART 재무제표 API (KR 재무지표)

| 항목 | 내용 |
|------|------|
| 용도 | KR 종목 재무지표 (매출, 영업이익, PER 등) |
| 현재 상태 | `financials.py`에 placeholder — `"KR 재무지표 DART 파싱 미구현"` 반환 |
| 엔드포인트 | `https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json` |
| 인증 | `DART_API_KEY` (공시와 동일 키) |
| 비고 | DART 재무제표는 XML/JSON 형태로 항목이 많아 파싱 로직 필요 |

### LLM API (AI 분석)

| 항목 | 내용 |
|------|------|
| 용도 | 뉴스/공시 → 키워드 자동 추출, AI 요약/피드백 생성 |
| 현재 상태 | AI 피드백 패널은 목업 텍스트. LLM 미연동. |
| 후보 | Claude API (Anthropic), OpenAI GPT, Azure OpenAI |
| 예상 구현 | 멀티 어댑터 패턴 — config로 provider 선택 |
| 환경변수 (예상) | `LLM_PROVIDER`, `ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY` |

### WebSocket (실시간 데이터)

| 항목 | 내용 |
|------|------|
| 용도 | 장중 실시간 호가/체결 데이터 |
| 현재 상태 | 미구현 |
| 후보 | 한국투자증권 OpenAPI (KR), Alpaca/Polygon.io (US) |
| 비고 | 인증 토큰 발급 필요, WebSocket 연결 유지 관리 |

### YouTube Data API (유튜브 의견 수집)

| 항목 | 내용 |
|------|------|
| 용도 | 주식 관련 유튜브 채널 의견/댓글 수집 |
| 현재 상태 | 미구현 (Phase 3) |
| 엔드포인트 | `https://www.googleapis.com/youtube/v3/` |
| 인증 | Google API Key |

### CNN/매크로 뉴스

| 항목 | 내용 |
|------|------|
| 용도 | 글로벌 매크로 뉴스 수집 + LLM 기반 종목 연관성 태깅 |
| 현재 상태 | 미구현 (Phase 3) |
| 후보 | NewsAPI, RSS 피드, 직접 크롤링 |

---

## 환경변수 요약

| 변수 | 필수 | 용도 | 발급처 |
|------|------|------|--------|
| `DATABASE_URL` | **필수** | PostgreSQL 연결 | 직접 설정 |
| `DART_API_KEY` | 선택 | 공시 + 재무 수집 | [DART OpenAPI](https://opendart.fss.or.kr/) |
| `NAVER_CLIENT_ID` | 선택 | 뉴스 수집 | [Naver Developers](https://developers.naver.com/) |
| `NAVER_CLIENT_SECRET` | 선택 | 뉴스 수집 | 상동 |

> 선택 항목 미설정 시 해당 Collector는 에러 메시지와 함께 0건 반환 (앱 정상 동작)
