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
- [x] SQLAlchemy async 모델 10개 테이블 (stocks, price_history, analyses, keyword_details, daily_keywords, favorites, news, disclosures, financials, exchange_rates)
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

## Phase 2 — LLM 연동 + 분석 자동화

- [ ] LLM 어댑터 설계 (Claude/GPT/Azure 멀티 지원)
- [ ] 뉴스/공시 → 키워드 자동 생성 파이프라인
- [ ] AI 요약/피드백 자동 생성 (분석 테이블 연동)
- [ ] 대화형 AI 질문 기능 (챗 인터페이스)

## Phase 3 — 데이터 확장

- [ ] KR 재무지표 DART 파싱 구현
- [ ] CNN/매크로 뉴스 수집 + LLM 기반 종목 연관성 태깅
- [ ] 유튜브 채널 의견 수집

## 인프라 + 운영

- [ ] 인증 시스템 (로그인/회원가입)
- [ ] 실시간 데이터 (WebSocket)
- [ ] 스케줄러 기반 자동 동기화 (현재는 수동 버튼)
- [ ] K8s 컨테이너 기반 배포 (AWS/Azure)
- [ ] CI/CD 파이프라인

## 개선사항

- [ ] 실제 DART/Naver API 키 설정 후 전체 동기화 테스트
- [ ] 프론트엔드 테스트 추가 (현재 백엔드만 있음)
- [ ] 에러 처리 UX 개선 (동기화 실패 시 토스트 등)
- [ ] 모바일 반응형 레이아웃
