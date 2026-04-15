# Tasks

## Phase 0 — 프로토타입 (2026-04-08) ✅

- [x] Next.js 15 + shadcn/ui + Tailwind 다크 테마 프론트엔드 셋업
- [x] 캔들+라인 차트 (lightweight-charts v5, 종가/MA5/MA20/MA60 토글)
- [x] 키워드 타임라인 + 상승/하락/보합 태그 + 상세 리포트
- [x] AI 피드백 패널 (목업 텍스트)
- [x] ⌘K 종목 검색 다이얼로그
- [x] 즐겨찾기 기능
- [x] 기간 탭 (일간~연간)
- [x] 재무지표 카드 (StatsCard)

## Phase 0.5 — PostgreSQL 연동 (2026-04-09) ✅

- [x] Docker Compose + PostgreSQL 서비스
- [x] SQLAlchemy async 모델 10개 테이블
- [x] Alembic 마이그레이션 설정
- [x] Mock → DB 전환 (API 라우터 리팩토링)
- [x] Seed 스크립트 (초기 종목 + 목업 데이터)

## Phase 1 — 실데이터 연동 (2026-04-09) ✅

- [x] stock_price collector (yfinance US / FinanceDataReader KR)
- [x] financials collector (yfinance US, KR DART 미구현)
- [x] news collector (Naver News API)
- [x] disclosure collector (DART 공시 API)
- [x] exchange_rate collector (open.er-api.com)
- [x] Admin sync API (종목별 / 글로벌 / 전체)
- [x] 프론트엔드 동기화 버튼 (종목별 + 전체)
- [x] stats를 financials 테이블에서 실시간 조회
- [x] 기간별 차트 데이터 범위 연동 (일간 30일 ~ 연간 3년)
- [x] 가격 on-demand 자동 수집 (DB 부족 시 외부 API 호출)
- [x] cmdk → 커스텀 Dialog 교체 (React 19 호환)
- [x] 분석 데이터 없을 때 graceful 처리
- [x] 백엔드 테스트 69개, 커버리지 98.5%
- [x] 구조 문서화 (ARCHITECTURE.md, CLAUDE.md)

---

## Phase 2 — LLM 연동 + 분석 자동화 (2026-04-13~14) ✅

### LLM 파이프라인
- [x] LLM 어댑터 인터페이스 (ABC) + Azure AI Foundry Responses API 구현
- [x] OpenAI 어댑터 (직접 OpenAI API용, 추후 전환 대비)
- [x] Analyzer: 뉴스/공시 → LLM → 키워드 자동 생성 파이프라인
- [x] 프롬프트 설계: 시니어 애널리스트 역할, 최소 8개 키워드, 구체적 수치/비교 포함
- [x] JSON 파싱 + 검증 (type/impact/duration 정규화)
- [x] 뉴스 URL → 키워드 source 자동 매칭 (LLM 의존 없이 DB 매칭)
- [x] Analysis UniqueConstraint (stock_id, date, period_type) 중복 방지
- [x] analysis API period_type 필터링 버그 수정
- [x] 동기화 시 LLM 분석 자동 실행 (llm_api_key 설정 시)

### 뉴스 수집 확장
- [x] US 종목 뉴스: yfinance news (10건) + NewsAPI.org (30건)
- [x] yfinance news 신규 포맷 대응 (content.title, canonicalUrl.url)
- [x] KR 종목 뉴스: Naver News API (50건)

### 인증 시스템
- [x] JWT 로그인 (POST /api/auth/login, GET /api/auth/me)
- [x] admin/user 역할 분리
- [x] Admin 엔드포인트 권한 체크 (require_admin)
- [x] .env 기반 초기 사용자 (ADMIN_EMAIL, ADMIN_PASSWORD)
- [x] 프론트엔드 로그인 UI + 토큰 관리 (localStorage)
- [x] admin만 동기화 버튼 노출

### 즐겨찾기 멀티유저
- [x] favorites에 user_id 컬럼 추가 + 마이그레이션
- [x] UniqueConstraint (stock_id) → (user_id, stock_id)
- [x] 전체 API/seed/scheduler 수정 (6곳+)
- [x] 첫 로그인 시 default 즐겨찾기 자동 복사

### 스케줄러
- [x] AsyncIOScheduler (8am/6pm KST)
- [x] 병렬 sync: 종목별 별도 AsyncSession + Semaphore(3)
- [x] FastAPI lifespan 연동 (시작/종료)
- [x] GET /prices on-demand sync 제거 (스케줄러가 대체)
- [ ] 실제 활성화 (.env SCHEDULER_ENABLED=true)

### 종목 자동등록
- [x] 검색 시 DB에 없으면 yfinance/FDR에서 외부 검색
- [x] 종목 페이지 접속 시 자동 등록 (_get_or_register_stock)
- [x] 한국 종목 .KS/.KQ 접미사 자동 시도
- [x] market 정규화 (NMS→NASDAQ, KSC→KRX 등)

### 코드 품질
- [x] pip → uv 패키지 관리 전환 (pyproject.toml + uv.lock)
- [x] get_stock_or_404 공유 의존성 추출 (DRY)
- [x] Pydantic response_model 전체 엔드포인트 적용 (13개 모델)
- [x] CORS origins config.py로 이동
- [x] alert() → Toast 컴포넌트 교체
- [x] 신규 테스트 51개 (adapter 12 + analyzer 12 + auth 15 + scheduler 6 + us_news 7)

### 프론트엔드
- [x] 로그인/로그아웃 UI (top-nav 드롭다운)
- [x] Toast 알림 컴포넌트 (성공/에러/정보)
- [x] 키워드 출처 URL 클릭 → 원본 기사 페이지 이동
- [x] 기간 탭: 차트만 변경, 키워드/AI피드백은 항상 최신 daily 분석 표시

### 문서
- [x] Quick Start 가이드 업데이트 (CLAUDE.md)
- [x] .env.example 생성
- [x] Phase 2 세션 리포트 (docs/gstack/)

---

## Phase 2.1 — 뉴스 본문 스크래핑 (2026-04-14) ✅

### 뉴스 본문 수집
- [x] News 테이블에 `content` (Text, nullable) 컬럼 추가 + 마이그레이션
- [x] `trafilatura` 기반 기사 본문 스크래퍼 (`collectors/scraper.py`)
- [x] 병렬 스크래핑 (Semaphore(5), 기사당 10초 타임아웃)
- [x] 스크래핑 실패 시 graceful fallback (뉴스 수집 결과 유지)

### API description 활용
- [x] Naver News API `description` → content 저장
- [x] NewsAPI.org `description`/`content` → content 저장
- [x] yfinance: 본문 없음 → 스크래핑으로 보완

### LLM 분석 품질 개선
- [x] LLM 프롬프트에 기사 본문 포함 (기사당 ~1000자 truncate)
- [x] 본문 없는 기사는 `(본문 없음)` 표시, 추론 방지 지침 추가
- [x] sync_news → scrape → analyze 파이프라인 통합

### 데이터 관리
- [x] 뉴스 본문 retention 정책 (30일 초과 content NULL 처리)
- [x] 스케줄러 sync job에 cleanup 자동 실행 통합
- [x] `NEWS_CONTENT_RETENTION_DAYS` 환경변수로 설정 가능

### 데이터 무결성
- [x] 가격 수집 `on_conflict_do_nothing` → `on_conflict_do_update` (재동기화 시 자동 복구)
- [x] 이상치 필터링 (전일 대비 300%+ 변동 시 스킵 + 경고 로그)

### 개발 편의
- [x] DEV_MODE 인증 바이패스 (백엔드 + 프론트엔드)
- [x] 프로덕션 배포 시 `DEV_MODE=false`로 전환

### 프론트엔드
- [x] keyword-timeline duplicate key 버그 수정

### 테스트
- [x] 신규 테스트 34개 (scraper 9 + us_news 10 + analyzer 13 + scheduler cleanup 2)

---

## Phase 2.5 — LangGraph Multi-Agent 대화형 AI (설계 완료, 구현 미착수)

Design doc: `~/.gstack/projects/feone90-stock-insight/main-design-20260415-langgraph-agents.md`

### Phase A: 대화형 Agent (다음 구현 대상)
- [ ] `langchain` + `langgraph` + `langchain-openai` 의존성 추가
- [ ] `create_agent` + `AzureChatOpenAI`로 Conversational Agent 구현
- [ ] Agent tools 6개 (get_stock_info, get_recent_prices, get_recent_news, get_analysis, search_stocks, get_financials)
- [ ] Chat API (POST /api/chat, SSE 스트리밍)
- [ ] `langgraph-checkpoint-postgres`로 대화 메모리
- [ ] /chat 페이지 (프론트엔드 Chat UI)

### Phase B: Multi-Agent 확장 (별도 설계)
- [ ] Research Agent (자율 뉴스 수집, 교차 검증)
- [ ] Analysis Agent (감성 분석, 재무 교차 검증)
- [ ] Supervisor (LLM 기반 라우터) 도입

### Phase C/D: 실시간 + 개인화 (별도 설계)
- [ ] WebSocket 실시간 가격, 급등/급락 알림
- [ ] 사용자 투자 성향 학습, 맞춤 추천

## Phase 3 — 데이터 확장 (미착수)

- [ ] KR 재무지표 DART 파싱 구현
- [ ] KR 공시 수집 활성화 (DART API 키 발급 필요)
- [ ] 기관/외국인 매매동향 (KRX 투자자별 매매)
- [ ] CNN/매크로 뉴스 수집 + LLM 기반 종목 연관성 태깅
- [ ] 유튜브 채널 의견 수집

## 인프라 + 운영 (미착수)

- [ ] DB 기반 사용자 관리 (현재는 .env)
- [ ] 실시간 데이터 (WebSocket)
- [ ] K8s 컨테이너 기반 배포 (AWS/Azure)
- [ ] CI/CD 파이프라인

## 개선사항

- [ ] 프론트엔드 테스트 추가 (Vitest + React Testing Library)
- [ ] 테스트 DB 격리 (conftest.py 트랜잭션 롤백)
- [ ] 모바일 반응형 레이아웃
- [ ] 종목 검색: US 종목 이름 검색 지원 (현재 티커만)
