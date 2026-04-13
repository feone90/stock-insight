# TODOS

## Test DB Isolation
- **What:** `conftest.py`에서 별도 테스트 DB URL + 트랜잭션 롤백 구현
- **Why:** 테스트가 개발 DB를 오염하고, 테스트끼리 간섭 가능. Phase 2에서 auth 테스트 추가되면 더 중요.
- **Effort:** CC ~15분
- **Depends on:** 없음
- **Added:** 2026-04-13 (eng review issue #1)

## Frontend alert() to Toast
- **What:** `stock-header.tsx`, `top-nav.tsx`의 `window.alert()` → shadcn/ui toast 컴포넌트로 교체
- **Why:** 설계 문서는 토스트 명시, 구현은 alert(). alert()는 브라우저 블로킹 + UX 나쁨.
- **Effort:** CC ~10분
- **Depends on:** 없음
- **Added:** 2026-04-13 (eng review issue)
