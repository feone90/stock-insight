# TODOS

## Test DB Isolation
- **What:** `conftest.py`에서 별도 테스트 DB URL + 트랜잭션 롤백 구현
- **Why:** 테스트가 개발 DB를 오염하고, 테스트끼리 간섭 가능. Phase 2에서 auth 테스트 추가되면 더 중요.
- **Effort:** CC ~15분
- **Depends on:** 없음
- **Added:** 2026-04-13 (eng review issue #1)

## ~~Frontend alert() to Toast~~ ✅ Done (2026-04-13)
- toast.tsx 컴포넌트 구현 완료. stock-header, top-nav 모두 교체됨.

## 스케줄러 실제 활성화
- **What:** `.env`에서 `SCHEDULER_ENABLED=true` 설정
- **Why:** 현재 수동 동기화만 가능. 매일 8am/6pm 자동 실행 필요.
- **Effort:** 설정 변경만
- **Added:** 2026-04-14

## DART API 키 발급
- **What:** https://opendart.fss.or.kr 에서 API 키 발급 → `.env`에 DART_API_KEY 설정
- **Why:** KR 종목 공시 수집이 안 되고 있음. LLM 분석 품질 향상에 필요.
- **Effort:** 5분
- **Added:** 2026-04-14

## 프론트엔드 테스트
- **What:** Vitest + React Testing Library 설정 + 핵심 컴포넌트 테스트
- **Why:** 프론트엔드 테스트 0개. auth/toast/search 등 핵심 플로우 커버 필요.
- **Effort:** CC ~30분
- **Added:** 2026-04-13 (eng review)
