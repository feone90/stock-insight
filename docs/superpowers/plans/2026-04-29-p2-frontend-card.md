# P2 — Frontend Card (Plan)

작성일: 2026-04-29
브랜치 (구현 시): `feat/v2-p2-frontend`
연관 문서:
- 메인 spec — `docs/superpowers/specs/2026-04-28-ontology-aware-stock-card-design.md` (§3 Card / §11 State / §18 Acceptance / §19 Phasing)
- backend 데이터 layer — `docs/superpowers/specs/2026-04-29-external-data-adapters.md` (P1.5 어댑터 산물이 카드 데이터 표면)
- 브레인스토밍 비주얼 산출물 — `.superpowers/brainstorm/2119-1777336204/content/04~13.html` (gitignored)

---

## 1. 목표

P1 backend가 produce하는 `StockCard` Pydantic 모델을 사용자가 실제로 읽는 카드로 만든다.

- 즐겨찾기 종목 1개를 누르면 7 섹션이 갖춰진 분석 카드가 보인다 (KR/US 동등)
- 라이트/다크 양쪽에서 정상 렌더
- 상태 (loading/empty/error/stale/partial/first-time) 모두 graceful degrade
- spec §18 acceptance 중 frontend 의존 항목 모두 그린

P3 (Stock Universe) / P4 (챗 슬라이드-업)에 진입할 수 있는 컴포넌트 anchor 제공이 P2의 또 하나의 책임. 즉 P2 자체는 카드 + 상태만, 그래프/챗은 placeholder + 네비게이션 hook만.

## 2. Design Principles (locked)

이 결정 8개는 spec 머지 시점에 확정. plan 시작 전 사용자 합의 필요할 항목은 §18 Open Questions로 분리.

1. **컴포넌트 단위 = 섹션** — 7 섹션 각각이 독립 React 컴포넌트. 섹션 간 의존 없음. 데이터 부족 시 섹션 단독 "데이터 부족" 폴백 (spec §11 Partial)
2. **데이터 진입점 = 단일 API** — `GET /api/cards/:ticker` 한 번으로 카드 전체 + citations + 상태 메타가 담긴 `StockCard` 응답 (spec §3)
3. **Hero chart는 기존 컴포넌트 재사용** — `frontend/src/components/stock/*` 의 lightweight-charts 차트를 카드 hero 영역으로 이식. 새 차트 컴포넌트 신규 작성 X
4. **다크 메인 + 라이트 토글** (spec §14 THEME). `prefers-color-scheme` 자동 + top-nav `☀/🌙`, localStorage 저장
5. **Citation 인터랙션** — `[n]` 클릭 시 같은 섹션 하단 source list로 스크롤 (D4). 전역 source list X
6. **카드 anchor 챗 (C option)** — footer "분석에 질문" 버튼이 슬라이드-업 패널 trigger. 패널 자체 본격 구현은 P4. P2는 ghost button + placeholder 모달까지
7. **Stock Universe 진입점만 (Y option)** — 관계 섹션의 "[그래프로 보기 →]" 링크는 placeholder 라우트 (`/universe/:ticker`) 등록만, 실제 그래프는 P3
8. **모바일 우선 carry forward** — 카드는 desktop ≥1024px 기준 디자인이지만 ≥375px (iPhone SE)에서도 1-column 폴백 동작 (spec §18 mobile acceptance)

## 3. 현재 상태 + 재사용

### Frontend 기존 자산 (spec §16 What Already Exists)
- `frontend/src/components/stock/*` — lightweight-charts v5 차트 (가격 + MA 라인 + 볼륨 바). hero chart로 재사용
- `frontend/src/services/api.ts` — API 클라이언트 패턴
- `frontend/src/services/auth.ts` — JWT
- `frontend/src/components/ui/*` — shadcn/ui primitives (버튼, 카드, 다이얼로그 등)
- Next.js 16 + React 19 + Tailwind CSS (다크 테마 이미 적용)
- `frontend/src/app/chat/` — P4에서 제거 대상 (P2 범위 X)

### Backend 기여 (P1 + P1.5에서 이미 머지됨)
- `GET /api/cards/:ticker` — `StockCard` 응답 (analysis_id, schema_version, persona_version, refresh_state 포함)
- `POST /api/cards/:ticker/refresh` — 강제 갱신 (cooldown 5분)
- 어댑터 layer — KR/US 동등 데이터 표면 (P1.5 Phase A/C/D)
- `enrich_stock_after_register` post-save hook — 신규 종목 추가 시 sector/peer 자동 (P1.5 Phase C)

### 기존 페이지/라우팅
- `/` — 대시보드 (즐겨찾기 종목 리스트)
- `/stock/[ticker]` — 종목 상세 (P1 시점 기존 차트 페이지)
- `/chat` — Phase A 챗 (P4에서 제거)

P2는 `/stock/[ticker]` 페이지를 v2 카드로 갈아끼우는 것이 본질. 기존 페이지는 v1 호환을 위해 path 변경 또는 query parameter (`?legacy=1`) 옵션 검토.

## 4. 라우팅 + 페이지 구조

### 4.1 새 라우트
```
/stock/[ticker]        ← v2 카드 (이번 P2)
/stock/[ticker]/legacy ← v1 호환 페이지 (선택, 한 번에 갈아끼우면 제거 가능)
/universe/[ticker]     ← P3 placeholder (404 또는 "준비 중")
```

### 4.2 페이지 layout

```
frontend/src/app/stock/[ticker]/page.tsx (rewrite)
  └── <StockCardPage ticker={ticker} />
        ├── <CardHeader />        ─ ticker · 한국어이름 · 영문명 · 시장 · 태그 · stance · 가격 · 변동 · asof
        ├── <HeroChart />         ─ lightweight-charts 재사용 + 1D/1W/1M✓/3M/1Y 토글
        ├── <AtAGlancePanel />    ─ Final Grade · Stance · Entry Stage 3 tile + one_line
        ├── <SectionList>         ─ 7 섹션 collapsible (D3: 종합의견 + 의사결정만 펼침)
        │     ├── <ThesisSection />
        │     ├── <TechMomentumSection />
        │     ├── <RelationsSection />     (with [그래프로 보기 →] link)
        │     ├── <NewsSection />
        │     ├── <MacroSection />
        │     ├── <FundamentalsSection />
        │     └── <DecisionSection />
        └── <CardFooter />        ─ refresh_state 배너 + 강제 갱신 + 분석에 질문
```

각 섹션 컴포넌트는 `compact` (1줄) + `expanded` (드릴다운) 두 모드. spec §3.2 표 그대로 매핑.

## 5. 데이터 흐름

```
┌──────────────────────────────────────────────────┐
│  /stock/[ticker]/page.tsx (Server Component)     │
│   → 초기 fetch: GET /api/cards/:ticker           │
│   → SSR로 카드 first paint                       │
└─────────────────┬────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────┐
│  <StockCardPage> (Client)                        │
│   - useStockCard(ticker) hook                    │
│     · SWR 캐시 (key = ticker)                    │
│     · refresh() = POST /refresh + revalidate     │
│   - useTheme() = 라이트/다크 + localStorage      │
└─────────────────┬────────────────────────────────┘
                  │
                  ▼
        7 섹션 컴포넌트가 카드 prop 분해해서 렌더
```

상태 매트릭스 (spec §11):
- `loading` — 스켈레톤 카드 + Perplexity-style 진행 로그
- `fresh` — 정상 렌더
- `stale` — 상단 노란 배너 + 강제 갱신 권고
- `error` — 마지막 성공 분석 + 빨간 배너
- `partial` — 가능 섹션만 렌더, 실패 섹션 collapse + 표시
- `first-time` — 신규 종목 미수집 시 "데이터 수집 + 분석 (~2분)" + 진행률 (이건 backend가 SSE로 진행 emit)

`refresh_state` enum (`fresh`/`stale`/`loading`/`error`)이 backend `StockCard.refresh_state`로 들어옴 — frontend는 그걸 보고 배너/스켈레톤 분기.

## 6. Design tokens (라이트/다크)

새 파일 `frontend/src/lib/design-tokens.ts` (spec §12). 카테고리 + 두 모드 매핑:

```typescript
export const tokens = {
  verdict: {
    BUY: { light: { bg: "...", fg: "...", border: "..." }, dark: {...} },
    WATCH: { light: {...}, dark: {...} },
    REJECT: { light: {...}, dark: {...} },
  },
  grade: { S: {...}, A: {...}, B: {...}, C: {...}, D: {...} },
  surface: { card: {...}, section: {...}, glance: {...} },
  cite: { bg: {...}, fg: {...} },
  chart: {                      // spec §12.3
    light: { close: "#0a8f3d", ma20: "#a06800", volumeUp: "#a8d8b8", grid: "#ececef" },
    dark:  { close: "#4ade80", ma20: "#fbbf24", volumeUp: "#1f4a2c", grid: "#1a1a22" },
  },
  relation: { peer: {...}, supply: {...}, group: {...}, theme: {...}, macro: {...} },
};
```

Tailwind: dark variant + CSS custom properties로 적용. `next-themes` 라이브러리 또는 직접 `useTheme` hook.

## 7. 컴포넌트별 상세

### 7.1 `<CardHeader />`
- ticker / 한국어이름 / 영문명 / 시장 (KRX/NASDAQ) / 태그 (≤3)
- stance verdict 배지 (한국어 라벨: 매수 후보/관망/보류, spec §3.4)
- 가격 + 변동 + 변동% + asof (KST)
- 모바일: 2-row stack

### 7.2 `<HeroChart />`
- lightweight-charts v5 instance
- 종가 line + MA20 dashed + 볼륨 bars (spec §3.1)
- 기간 토글 1D/1W/1M✓/3M/1Y
- 차트 토큰 (라이트/다크 분기)
- **기존 차트 컴포넌트 ref 추출 + props만 갈아끼움** — 큰 변경 없이 재사용

### 7.3 `<AtAGlancePanel />`
- 3 tile: Final Grade (A~D + 어제 대비 ↑↓) / Stance / Entry Stage
- 한 줄 요약 (`glance.one_line`) + inline `[n]` citations
- 강조: 보라 surface + 큰 폰트

### 7.4 7 섹션 (`<SectionShell>` 추상화)

공통 shell:
- 헤더 (이모지 + 제목 + 우상단 collapse 토글)
- compact body (1줄, spec §3.2)
- expanded body (드릴다운)
- 섹션 끝에 source list (해당 섹션 citation만)

각 섹션은 shell + 자기 데이터 적용:

| 컴포넌트 | spec §3.2 매핑 | 추가 동작 |
|---|---|---|
| `<ThesisSection>` | core_thesis + supports/opposes + catalysts + scenarios | 시나리오 BULL/BASE/BEAR 가로 bar, catalysts 빈 시 `no_catalysts_reason` 표시 |
| `<TechMomentumSection>` | RSI / MA stack / RVOL20 + 추가 지표 | summary_line + interpretation 라벨 (model_generated/rule_based) |
| `<RelationsSection>` | peer/공급망/테마 1줄 | 상세는 표 + "[그래프로 보기 →]" → `/universe/:ticker` (P3 placeholder) |
| `<NewsSection>` | 뉴스 토픽 1줄 + impact emoji | 최근 N일, dedup, 본문 요약 |
| `<MacroSection>` | VIX / FX / 미 10Y 1줄 | factor β + 임박 매크로 일정 |
| `<FundamentalsSection>` | PER / PBR / 시총 | 5y z-score + 동종 평균 + 배당 |
| `<DecisionSection>` | stance + risk_threshold + 한 줄 | scenarios 확률 + 추정 손익비 + "참고용" 면책 (spec §3.4 D5) |

D3에 따라 종합의견 + 의사결정만 default 펼침, 나머지 접힘.

### 7.5 `<CardFooter />`
- `refresh_state` 배너 (stale 시 노란, error 시 빨간)
- 마지막 분석 시각 + 출처 N건
- "강제 갱신" 버튼 — 5분 cooldown (backend가 enforce, 클라이언트는 disabled state만)
- "분석에 질문" 버튼 — 슬라이드-업 패널 trigger (P2에서는 placeholder 모달, P4에서 본격)

## 8. Citation 인터랙션 (D4)

- 모든 numerical claim에 inline `<CitationBadge n={3}>[3]</CitationBadge>`
- 클릭 시 같은 섹션 source list의 해당 row로 scroll + 하이라이트 (1초)
- source list는 섹션 끝에 dl/dt/dd 또는 list로 렌더 — `(source_type, label, url, timestamp)` 표시
- footer의 "12개 출처" 합산 N — 모든 섹션 citations dedup

## 9. 상태 컴포넌트

### 9.1 `<CardSkeleton />`
- 7 섹션 placeholder + shimmer
- Perplexity-style live updates: `<ProgressLog>` 컴포넌트 — backend SSE에서 step ("리서치 시작 → 뉴스 수집 → 매크로 → 시너프 →") emit 받아서 표시

### 9.2 `<EmptyDataCard />` (first-time)
- "이 종목 처음입니다 — 데이터 수집 + 분석 (~2분)"
- 진행률 bar
- backend SSE로 `data_layer.assemble_data_layer` 진행 emit

### 9.3 `<ErrorBanner />`
- 마지막 성공 분석 표시 + "최근 분석 실패 — 재시도" 빨간 배너
- 재시도 클릭 → POST /refresh

### 9.4 `<StaleBanner />`
- "분석 N시간 지남 — 갱신" 노란 배너
- 자동 갱신 시각 표시 (다음 KR/US 스케줄 시점)

### 9.5 `<PartialDataNotice />` (섹션 단위)
- 섹션 헤더에 "데이터 부족 — 외부 리서치 진행 중" 인라인
- 섹션 collapse 유지

## 10. API 클라이언트

`frontend/src/services/api.ts` 확장:

```typescript
export async function fetchStockCard(ticker: string): Promise<StockCard>;
export async function refreshStockCard(ticker: string): Promise<StockCard>;
export function streamCardProgress(ticker: string): EventSource;  // SSE for first-time + loading
```

`StockCard` TypeScript type — backend Pydantic schema에서 자동 생성. 옵션:
- (a) 수동 타입 작성 (적은 schema 변동, ~150 line)
- (b) `pydantic-to-ts` 또는 `openapi-typescript` 자동 생성 (CI 통합)

P2에서는 (a) 수동. P5 polish에서 (b) 자동화.

## 11. 테스트 plan

### 단위 (~25 cases)
- `<CardHeader>` — verdict 배지 매핑, 모바일 stack
- `<AtAGlancePanel>` — Grade 변화 표시 (↑↓), one_line citation 렌더
- `<ThesisSection>` — 시나리오 BULL/BASE/BEAR 정렬, catalysts 빈 케이스 + `no_catalysts_reason`
- `<RelationsSection>` — peer/supply/theme 1줄 압축, 상세 펼침
- `<DecisionSection>` — "참고용" 면책 항상 표시
- `<CitationBadge>` — 클릭 → scroll target 매핑
- `<CardSkeleton>` / `<EmptyDataCard>` / `<ErrorBanner>` / `<StaleBanner>` — props 따라 분기
- `useStockCard` hook — SWR 캐시, refresh revalidate
- `useTheme` hook — localStorage + system preference

### 시각 회귀 (~10 snapshots)
- 라이트/다크 × 7 섹션 = 14
- 모바일 (375px) full card 1
- partial state (한 섹션 데이터 부족) 1

도구: `@chromatic-com/storybook` 또는 Playwright screenshot. 첫 ship에는 Playwright만 (Storybook 도입은 P5).

### E2E (~5 flows)
- 종목 페이지 진입 → 카드 fresh 렌더
- 강제 갱신 클릭 → 5분 cooldown 적용 (disabled state)
- 다크 → 라이트 토글
- 모바일 viewport (375px) → 1-column 폴백
- error state → 재시도 버튼 작동

### 회귀
- 기존 차트 컴포넌트 분리 후 재사용한 hero chart가 v1 페이지 동작 안 깨뜨림

## 12. Sub-phase 분해

총 ~1.5주. sub-phase 단위 commit/PR.

| Sub-phase | 내용 | 예상 |
|---|---|---|
| **A** | design-tokens + 라이트/다크 토글 + scaffold (`<StockCardPage>` shell + 7 섹션 빈 컴포넌트) | 1일 |
| **B** | API 클라이언트 + `useStockCard` hook + `<CardHeader>` + `<HeroChart>` 재사용 + `<AtAGlancePanel>` | 2일 |
| **C** | 7 섹션 compact + collapsible (D3 default 펼침/접힘) | 2일 |
| **D** | 7 섹션 expanded + citation drilldown + source list + `<CitationBadge>` | 2일 |
| **E** | 상태 매트릭스 (loading/empty/error/stale/partial/first-time) + SSE 진행 로그 | 1.5일 |
| **F** | `<CardFooter>` + 강제 갱신 cooldown + 분석에 질문 placeholder + `/universe/:ticker` placeholder + E2E + 시각 회귀 | 1.5일 |

## 13. Acceptance criteria (P2 머지 시점)

spec §18 acceptance 중 frontend 의존 항목 모두 그린:

- [ ] 즐겨찾기 KR 종목 1개 (`005930`) 분석 카드 7섹션 모두 렌더
- [ ] 즐겨찾기 US 종목 1개 (`TSLA`) 동일 (KR/US 동등 — 메모리 §kr_us_equal_priority)
- [ ] 모든 numerical claim에 [n] 인용 + 클릭 시 같은 섹션 source list scroll
- [ ] 지지근거 ≥3, 반대근거 ≥2, 시나리오 3개 표시 (backend가 강제하지만 frontend도 graceful)
- [ ] 14일 내 catalyst 있으면 표시, 없으면 "확인된 임박 일정 없음" 명시 (강제 fabricate UI X)
- [ ] 라이트 + 다크 토글 양쪽 정상 렌더 (시각 회귀 14 snapshots green)
- [ ] 강제 갱신 버튼 5분 cooldown 동안 disabled state
- [ ] 분석 실패 시 stale data fallback + 빨간 배너
- [ ] 모바일 (375px) 1-column 폴백
- [ ] `/chat` 페이지 진입점은 P4까지 유지하되 카드 footer "분석에 질문"이 placeholder 모달 trigger
- [ ] `/universe/:ticker` placeholder 라우트 (P3 anchor만)
- [ ] UI 카피 금지어 검증 정규식 통과 ("워렌버핏" 등 — spec §18 마지막 항목)
- [ ] 라이트/다크 양쪽 텍스트 vs surface 배경 contrast ≥4.5:1 (verdict 배지 포함, §17.3)
- [ ] 폰트 크기 시스템 (모바일 base 16px / 데스크탑 base 14px, §17.2) 적용
- [ ] 모든 인터랙티브 element 모바일 터치 target ≥44×44px (citation/footer 버튼/collapse 토글/기간 토글, §17.4)
- [ ] citation `[n]` 클릭/탭 동작 동일 (모달 X, 같은 섹션 source list scroll + 1초 하이라이트, §17.5)
- [ ] asof 표시 = 절대 시각 + hover/tap 시 상대 시각 tooltip (§17.5)

## 14. Out of scope (P3+로 위임)

- **Stock Universe 시각화** (react-force-graph-2d) → P3
- **카드 anchor 챗 패널 본격 구현** (슬라이드-업, tool 4개) → P4
- **eval harness UI** → P5 (P5는 backend eval `eval_card_quality.py`, frontend는 결과 surface만)
- **이력 비교** ("어제 BUY → 오늘 WATCH 왜?") — v2.1+ (spec §15)
- **포트폴리오 뷰** — v2.1+
- **수동 큐레이션 UI** — 영구 deferred (사용자 명시 거부, spec §15)
- **TypeScript 타입 자동 생성** (pydantic-to-ts / openapi-typescript) — P5

## 15. Risks & Open Questions

| 항목 | 영향 | 대응 |
|---|---|---|
| `frontend/src/components/stock/*` 차트가 v1 페이지 의존성 강하면 재사용 어려울 수 있음 | hero chart 신규 작성 시 ~1일 추가 | sub-phase B 시작 시 첫 1시간 spike로 재사용성 확인. 어려우면 fork |
| Next.js 16 SSR + lightweight-charts v5 호환 | hero chart 깨짐 | dynamic import + `ssr: false` 옵션 |
| 카드 데이터가 큰 경우 (40개 citation, 시나리오 본문 등) 모바일 인지 부담 | UX 저하 | progressive disclosure (D3) — 종합/의사결정만 펼침 |
| 시각 회귀 도구 선택 (Playwright vs Chromatic) | 도구 도입 비용 | P2는 Playwright만 (간단), Chromatic은 P5 |
| `analysis_id` versioning UI 표시 | 사용자 혼란 | P2에서 noop, P5 polish에서 footer에 "schema v2 / persona v1" 표시 옵션 |
| chat placeholder가 P4 본격 구현으로 잘 매끄럽게 전환되나 | 카드 anchor 챗 UI 변경 | placeholder를 BottomSheet primitive로 만들고 P4에서 내부만 채우기 |

**Open Question 1**: 기존 `/stock/[ticker]` v1 페이지를 머지 시 그대로 갈아끼울지 / `?legacy=1` 옵션 유지할지 → sub-phase F 시점 결정. 기본은 그대로 갈아끼움 (가족 4명용이라 마이그레이션 부담 적음).

**Open Question 2**: SSE 진행 로그를 frontend에서 표시할지 / backend log만 충분할지 → sub-phase E 시작 시 backend SSE endpoint 존재 확인. 없으면 P5로 위임.

## 16. Dependencies + Constraints

### Backend 사전 요구
- ✅ `GET /api/cards/:ticker` — P1에서 머지됨
- ✅ `POST /api/cards/:ticker/refresh` — P1에서 머지됨
- ✅ KR/US 동등 데이터 표면 — P1.5 어댑터 layer
- ⚠️ SSE 진행 stream — 존재 여부 sub-phase E 시작 시 확인. 없으면 frontend는 spinner만 (P5에서 SSE 구현)

### Frontend 의존성 추가
- 없음 — Next.js 16 + React 19 + Tailwind + lightweight-charts v5 + shadcn/ui 모두 기존
- (선택) `next-themes` — useTheme hook에 사용. 없으면 직접 구현 (~30 line)

### Constraints
- 모든 사용자 향 UI 텍스트는 한국어 (메모리 §korean_user_facing_text)
- 코드 identifier / commit / log 메시지는 영어 (CLAUDE.md)
- spec §6.4 금지어 ("워렌버핏", "전문가급", "강력 매수", "확실한 수익") UI 카피 0건

---

## 17. Design quality + 반응형 specs (plan-design-review patch)

P2 plan-design-review (2026-04-29) 결과 add-on. 디자인 품질 + 반응형 디테일을 plan-time에 락인. 시각장애/색맹 a11y는 가족 사용자 시나리오에서 out of scope (사용자 명시).

### 17.1 Breakpoints

| 이름 | min-width | 대상 |
|---|---|---|
| `mobile` | 375px | iPhone SE / Android |
| `tablet` | 768px | iPad portrait |
| `desktop` | 1024px | 일반 노트북 |
| `wide` | 1280px | 외장 모니터 |

기준: ≥375px에서 1-column 폴백 작동, ≥1024px에서 hero chart + glance 패널 가로 배치.

### 17.2 폰트 크기 시스템

| 토큰 | 모바일 (≤768) | 데스크탑 (≥1024) |
|---|---|---|
| `text-h1` (ticker, 가격) | 24px | 28px |
| `text-h2` (섹션 헤더) | 20px | 22px |
| `text-h3` (sub-section) | 18px | 20px |
| `text-body` | 16px | 14px |
| `text-caption` | 14px | 13px |
| `text-citation` (`[n]` 배지) | 12px | 12px |

근거: 모바일은 viewing distance가 가까워 base 16px, 데스크탑은 더 멀어 14px. h1은 모든 viewport에서 stance/티커 강조 위해 동일하게 큼.

### 17.3 컬러 contrast 검증

- 라이트 / 다크 양쪽에서 텍스트 vs surface 배경 contrast ratio **≥4.5:1** (가독성 표준, 일반 사용자 다크모드 가독성 보장 — 시각장애 a11y와 무관)
- verdict 배지 (BUY 녹색 / WATCH 노랑 / REJECT 빨강) — 배지 배경 vs 텍스트 ≥4.5:1
- 차트 토큰 (spec §12.3) — line color vs grid color 시각적 분리

검증: sub-phase F의 Playwright 시각 회귀에서 contrast 자동 체크 hook (`axe-core` 또는 `pa11y` import — 별도 도구 도입 X, 기존 Playwright runner에 한 번 invoke).

### 17.4 터치 target ≥44px (모바일)

- citation `[n]` 배지: 폰트 12px이지만 padding으로 클릭 영역 ≥44×44px
- 강제 갱신 / 분석에 질문 footer 버튼: ≥44×44px
- 섹션 collapse 토글: ≥44×44px
- 기간 토글 (1D/1W/1M/3M/1Y): ≥44×44px
- 다크/라이트 토글: ≥44×44px

근거: 손가락 터치 정확도 표준. desktop은 클릭 영역 작아도 OK이지만 같은 컴포넌트라 모바일 기준 적용.

### 17.5 인터랙션 형식

- **citation `[n]`**: 클릭/탭 동작 동일 (모바일/데스크탑) — 같은 섹션 source list로 scroll + 1초 하이라이트. 모달/popup X (인지 부담 회피 + 일관성)
- **asof 표시**: 절대 시각 + 상대 시각 둘 다
  - 평소: 절대 시각 (`2026-04-29 14:23 KST`)
  - hover (desktop) / tap (mobile) 시: 상대 시각 (`2시간 전`) tooltip
- **기간 토글**: 즉시 차트 갱신 (데이터는 이미 fetch됨, render만 → loading skeleton 0.3s 미만)

### 17.6 hero chart 모바일

- desktop (≥1024px): width 100%, height 320px
- 모바일 (≤768px): width 100%, height 240px (3:2 비율 유지, header + glance 보이게)
- 차트 ToolTip (가격/날짜): 터치 시 상단 고정 (손가락이 ToolTip 가리는 거 방지)

---

## 다음 단계

1. (선택) plan-eng-review 받기 — frontend 영역 review가 적합한지 검토. design-review 또는 plan-design-review 별도 가능
2. plan PR 생성 + 머지
3. sub-phase A 시작 — `feat/v2-p2-frontend-a-tokens` 브랜치 분기
4. A → B → C → D → E → F 순차 진행 (각 sub-phase 별도 commit/PR 또는 통합)

작업량 추정: **~1.5주** (10 working days). spec §19 추정과 일치.
