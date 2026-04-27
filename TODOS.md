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

## test_admin_api.py::test_sync_stock skip 해제
- **What:** `tests/test_admin_api.py::test_sync_stock`이 `@pytest.mark.skip`로 막혀 있음. SAVEPOINT setup에서 "Future attached to a different loop" RuntimeError. 파일 내 첫 async 테스트가 session-scoped engine과 function-scoped event loop 사이 mismatch로 깨지는 패턴.
- **Why:** 사전 인프라 이슈 (Phase A 작업과 무관). happy path는 같은 파일 `test_sync_stock_with_errors`가 커버 중이라 ship 영향은 없으나, 회귀 가드는 약화됨.
- **시도 가능한 fix:** `asyncio_default_fixture_loop_scope = "session"` 시도했으나 다른 60+ 테스트가 깨짐 → 더 깊은 fixture 리팩토링 필요. conftest의 `event_loop` session 스코프 fixture를 신형 pytest-asyncio API로 마이그레이션하거나, `db`/`client` fixture를 세션 스코프 connection pool과 호환되게 재작성.
- **Effort:** CC 30~60분
- **Added:** 2026-04-27
- **What:** Vitest + React Testing Library 설정 + 핵심 컴포넌트 테스트
- **Why:** 프론트엔드 테스트 0개. auth/toast/search 등 핵심 플로우 커버 필요.
- **Effort:** CC ~30분
- **Added:** 2026-04-13 (eng review)

## [Phase 2.5 전제조건] Azure Foundry Responses API function calling smoke test
- **What:** 기존 `AzureOpenAIAdapter`에 tool calling을 실험적으로 추가해 Foundry Responses API가 function calling을 지원하는지 5-10분 smoke test. Microsoft Learn docs 또는 직접 호출로 확인.
- **Why:** Phase A는 이 adapter를 확장해 `chat_with_tools()`를 만들 계획. Foundry Responses API가 tools/function_call을 아예 지원 안 하면 Phase A 전체가 blocker. LangGraph/AzureChatOpenAI 경로로 fallback 필요해짐.
- **Context:** adapter.py:34에서 body에 `tools` 필드 추가해보고 응답에 tool_call이 포함되는지 확인. 실패 시 design doc에 fallback 경로 추가.
- **Depends on:** 없음 (Phase 2.5 Phase A 시작 전 반드시)
- **Effort:** CC ~10분
- **Added:** 2026-04-16 (Phase 2.5 Phase A eng review)

## [Phase 2.5 전제조건] chat_messages 테이블 Alembic migration
- **What:** Phase A에서 사용할 `chat_messages(id, thread_id uuid, user_id str, role str, content text, tool_calls jsonb, created_at timestamptz)` 모델 추가 + migration 생성.
- **Why:** LangGraph checkpointer 대신 SQLAlchemy 기반 단순 테이블로 대화 이력 저장. 기존 asyncpg 드라이버만 사용 → 3개 드라이버 공존 회피.
- **Depends on:** 없음
- **Effort:** CC ~10분
- **Added:** 2026-04-16 (Phase 2.5 Phase A eng review)

## ~~[Phase 2.5 출시 전] 한국어 tool selection eval~~ ✅ Done (2026-04-27)
- 19/20 PASS (95%), ship gate ≥ 80% 통과.
- Harness: `backend/scripts/eval_chat_tools.py` — `uv run python -m scripts.eval_chat_tools`
- 리포트: `docs/gstack/phase-a-eval-20260427-092834.md`
- 단일 실패 (#12 "네이버 주가 흐름 어때?"): seed 이름이 영문 `NAVER`라 한글 search miss → 한 번 만에 포기. LLM 비결정성 — #6/#11에서는 영문 재시도 후 통과. **후속:** seed에 한국어 alias 추가하거나 search_stocks에 ko↔en 매핑 보강.
