# Design Audit — 2026-05 (가족 demo polish, 옵션 D)

## 컨텍스트 (먼저 읽고 시작)

이 작업은 **별도 세션에서 fresh context로** 수행한다. 데이터 파이프 (재무 / 뉴스 / 관계 / 근거)는 끝났고, 카드/그래프 모두 작동한다. 남은 건 **가족이 처음 봤을 때의 시각 인지** — empty state가 친절한지, 의사결정 블록이 한눈에 들어오는지, 정치 시그널 같은 특수 셀이 눈에 띄는지.

UI는 다크 모드 강제 (`globals.css` `body { background-color: oklch(0.145 0 0); color: oklch(0.985 0 0); }`). 한국 시장 색상 관습 — **빨강=상승, 파랑=하락**. 사용자 향 텍스트는 전부 한국어, 코드/커밋만 영어. 종목: 005930 삼성전자 / 042700 한미반도체 / 240810 원익IPS / 950160 코오롱티슈진 / TSLA 등이 demo 모집단.

이전 세션에서 사용자가 명시적으로 합의한 우선순위는 **옵션 D = audit 항목 1, 2, 4** (총 ~30분). 본 문서는 그 세 항목만 다룬다.

## 작업 범위 (3개, 이 외 손대지 말 것)

### 1. Main page empty state — 종목 추천 + 검색 CTA 강조 (10분)

**현재 상태:** 즐겨찾기 0건일 때 메인 페이지(`frontend/src/app/page.tsx`)가 비어보임. 사용자가 "뭘 해야 하지" 막막.

**파일:** `frontend/src/app/page.tsx`. 즐겨찾기 list 렌더 분기에서 `favorites.length === 0` 케이스만 손댄다.

**목표:**
- 큰 친절한 제목 ("처음 보시나요?" 같은 톤, 단 cheesy 금지)
- 한 줄 설명 (Ctrl+K로 종목 검색하면 카드 자동 생성된다는 메커니즘 설명)
- **추천 3종목** 카드 (삼성전자 005930 / SK하이닉스 000660 / TSLA) — 클릭하면 `/v2/stock/{ticker}` 이동
- 키보드 hint badge (`⌘K` 또는 `Ctrl+K`)
- 다크 모드 + 모바일 반응형 (3종목이 모바일에선 vertical stack)

**시각 가이드:**
- 제목: `text-2xl md:text-3xl font-bold tracking-tight`
- 추천 카드 grid: `grid grid-cols-1 md:grid-cols-3 gap-3`
- 추천 카드: surface elevation (`bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-xl p-4 hover:border-blue-500/40`)
- 키보드 hint: `inline-flex items-center gap-1 text-xs border border-[var(--surface-border)] rounded px-1.5 py-0.5 font-mono`
- emoji / 그래픽 금지. 텍스트 + border만으로 차별.

**Acceptance:**
- 즐겨찾기 0일 때만 표시. 1건 이상이면 기존 list 그대로
- 추천 3종목 클릭 → 카드 페이지 이동 (자동 분석 트리거는 다음 세션 D 작업이라 이 spec 범위 X)
- 다크 모드, 모바일 (375px) 확인

### 2. 종합 의견 + 의사결정 블록 강조 (10분)

**현재 상태:** `thesis-section.tsx` (종합 의견) 와 `decision-section.tsx` (의사결정) 둘 다 일반 섹션처럼 보임. 사용자가 카드 스크롤하면서 "결국 사야 돼 말아야 돼" 찾기 어려움.

**파일:**
- `frontend/src/components/stock-v2/thesis-section.tsx` — "종합 의견" 섹션
- `frontend/src/components/stock-v2/decision-section.tsx` — "의사결정" 섹션
- `frontend/src/components/stock-v2/section-shell.tsx` — `highlight` prop에 `"decision"` 또는 새 variant 추가해 두 섹션이 같은 강조 토큰 공유

**목표:**
- 두 섹션의 expanded 상태에서 **좌측 vertical accent stripe** (4px) + 살짝 더 진한 surface bg.
- accent 색상은 stance에 따라: BUY=red, WATCH=amber, REJECT=blue (이미 `STANCE_BG` 토큰 있음, 재사용).
- compact 상태에서도 stance 색상 라벨/뱃지가 또렷.

**시각 가이드:**
- accent stripe: `before:absolute before:left-0 before:top-3 before:bottom-3 before:w-1 before:rounded-r` + stance 색상
- surface bg subtle bump: `bg-[var(--surface-glance)]` 또는 `bg-[var(--surface-card-elevated)]` (없으면 추가 토큰 1개)
- 두 섹션 폰트는 그대로. **읽기 부담 추가 금지** — emphasis는 "edge / margin / position"으로만.

**Acceptance:**
- 카드 위에서 두 섹션이 시각적으로 같은 그룹으로 묶여 보임 (다른 섹션과 구분)
- stance가 BUY일 땐 빨강 stripe, REJECT 파랑, WATCH 앰버 — 카드 헤더의 stance badge와 동일 색상
- 모바일에서 stripe가 깨지지 않음

### 3. 정치 시그널 amber border 강화 (5분)

**현재 상태:** Truth Social 정치 발언이 매핑된 종목 카드에서 `news-section.tsx`가 amber 처리하는데 border가 1px / 단색 — 다른 뉴스와 구분이 약함.

**파일:** `frontend/src/components/stock-v2/news-section.tsx` — political signal 분기 컴포넌트만.

**목표:**
- border 두께 1px → 2px
- **좌측 vertical stripe** (3px, amber-500)로 "특수 카테고리" 시각화
- "정치 시그널" 라벨 (텍스트 또는 작은 ⚡ icon — 추가 emoji는 금지하니까 텍스트 badge로) — `bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30 px-1.5 py-0.5 rounded text-[10px] font-semibold`

**시각 가이드:**
- 컨테이너: `relative border-2 border-amber-500/40 dark:border-amber-500/30 rounded-md pl-3` + `before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px] before:bg-amber-500 before:rounded-l-md`
- 다른 뉴스 row와 시각적 거리 — 별도 `space-y` 또는 약간의 outer padding

**Acceptance:**
- 정치 시그널 있는 종목 (예: AAPL, TSLA가 Trump 발언으로 매핑됐던 경우) 카드 새로고침 → 뉴스 섹션에서 즉시 눈에 띔
- 정치 시그널 없는 종목 카드는 변화 없음
- 다크 / 라이트 둘 다 확인 (라이트는 사용 빈도 낮지만 일관성 유지)

## 절대 손대지 말 것

- 데이터 파이프 (collectors/, services/) — 백엔드 작업 진행 중. 백엔드 코드 일체 수정 X.
- `relations-section.tsx`의 rationale row — 이전 세션에서 마무리됨.
- `ontology-graph.tsx` — 이전 세션에서 마무리됨.
- `hero-chart.tsx` 색상 — 한국 관습 (빨강=상승) 이미 적용됨, 절대 swap X.
- 기존 STANCE_BG / GRADE_FG / IMPACT_COLOR 토큰 — 재사용하되 신규 정의 X (불일치 방지).

## 검증 방법

1. `cd frontend && npm run dev` (또는 Vercel preview 사용)
2. 다크 모드 강제 확인 (이미 `globals.css`로 강제됨)
3. 데스크탑 (1440px), 태블릿 (768px), 모바일 (375px) 셋 다 확인
4. demo 종목 카드 / 메인 페이지 둘 다 열어 시각 확인
5. type check: `cd frontend && npx tsc --noEmit` — 새 prop 추가 시 타입 통과 필수

## 커밋 / push

- 모든 작업은 한 commit으로 묶어도 되고 작업 항목별로 3 commits 해도 됨.
- 커밋 메시지 영어, 사용자 향 텍스트 한국어.
- push 시 `git push origin main && git push fork main` (양쪽 모두 — Vercel은 fork 감시).
- Co-authored-by Claude Opus 4.7 trailer 유지.

## 후속

- 이 spec 완료 후 메모리 entry `project_design_audit_pending.md` 를 "shipped" 상태로 업데이트하거나 삭제.
- audit top 7 중 3개 미처리 (`#3 at-a-glance prominence` / `#5 empty fundamentals` / `#6 badge styling` / `#7 mobile reflow`) 는 별도 세션 후보. 사용자 결정 받고 진행.
