# Ontology Architecture (Spec)

작성일: 2026-04-30
연관: 메인 spec `2026-04-28-ontology-aware-stock-card-design.md` (§3 Card / §9 Stock Universe / §15 Out of Scope)
관련 메모리: `feedback_ontology_product_model.md`

이 spec은 메인 spec의 ontology 측면 deep dive. 메인 spec에서 §3·§9가 단일 layer로 가정한 모델을 3-layer로 재정의하고, relation 표현력을 확장하며, 자동 추출 pipeline을 구체화한다.

---

## 1. Problem

메인 spec 머지 후 P1.5 어댑터 + P2 frontend 진행하면서 **사용자가 직접 짚은 architectural 부족분**이 4가지 드러남:

1. **Universe vs User favorites 혼동** — 메인 spec은 "즐겨찾기 종목 + 그 종목 분석으로 형성된 ontology" 가정. 단 즐겨찾기는 가족 5-50개에 그쳐 ontology가 sparse + 닫힌 회로 (사용자 알던 sector만)
2. **Relation 표현력 빈약** — 6 type (peer / supply_upstream/downstream / group / theme / macro)으로 "B 호재 → A 수혜" 같은 zero-sum 패턴 표현 불가. 매수/매도 신호 source인데 빠짐
3. **Manual curation 영구 deferred 결정의 약점** — 자동 path가 명확하지 않으면 ontology 데이터 빈약. 단 자동 추출 (DART 공시 LLM RAG + SEC 8-K + 뉴스)이 가능한데 spec에 명시 없음
4. **Universe 선정 기준 미정** — "어떤 종목이 ontology에 들어가나"가 메인 spec에서 모호. 가족 관심 sector 위주는 닫힌 회로 위험

이 spec은 위 4 부족분을 해결한다.

---

## 2. Locked Principles (8개)

이 8개는 사용자와 align 완료. 변경 시 본 spec 다시 봐야.

1. **3 Layer 분리** — Reference Universe (시장 객관 메타) / Ontology (관계 그래프) / User Favorites (우선순위 only)
2. **Ontology = 발견의 원천** — 사용자가 모르던 종목 surface가 본질. 매수/매도 신호 source
3. **Universe 객관 기준** — 시총/index + GICS sector quota. 가족 관심 sector 위주 ❌
4. **즐겨찾기 = LLM 비용 영역** — ontology와 무관 layer
5. **비용 모델** — universe seed + ontology cross-match + LLM RAG ~$10/month, 카드 분석은 즐겨찾기만
6. **Relation 표현력** — Signed weighted directed graph (`signal_direction` / `confidence` / `valid_period` / `metadata`)
7. **자동 추출 pipeline** — DART 공시 / SEC 8-K / 뉴스 / web / 가격 상관관계 5 source. Manual curation 영구 deferred 유지
8. **LangGraph/RAG 미래 trigger** — 지금은 plain Python async + 직접 ReAct loop. migration 친화적 architecture 유지

---

## 3. Architecture — 3 Layer 모델

```
┌──────────────────────────────────────────────────────┐
│  Reference Universe (~900 종목, 메타 only)            │
│   - KR: KOSPI 200 + KOSDAQ 200 (시총/index 기반)     │
│   - US: S&P 500 (index membership)                  │
│   - 추가: GICS sector 11개마다 minimum 30종목 quota   │
│   - 데이터: ticker / name / market / sector /        │
│            industry_group / market_cap / liquidity   │
│   - 자동 nightly refresh (시총 변동 반영)            │
│   - 비용 0 (P1.5 어댑터 활용)                         │
└─────────────────────┬────────────────────────────────┘
                      │ universe-wide cross-match
                      ▼ (외부 API/LLM 비용 0)
┌──────────────────────────────────────────────────────┐
│  Ontology Graph (관계망)                              │
│   Nodes = Reference Universe 종목 + 매크로 factor     │
│   Edges = stock_relations row                        │
│     - relation_type: peer / supply_* / group /       │
│                      theme / macro / competitor /     │
│                      contract_supplier/customer /     │
│                      complementary / regulatory_link │
│     - signal_direction: positive / negative / inverse│
│     - strength + confidence (분리)                   │
│     - valid_from / valid_until / is_active           │
│     - source: auto_sector_match / dartlab_industry / │
│               disclosure_explicit /                   │
│               llm_extracted_news / ...               │
│     - metadata jsonb (액수, 기간, source URL)        │
└─────────────────────┬────────────────────────────────┘
                      │ highlight + 본격 분석 비용 영역
                      ▼
┌──────────────────────────────────────────────────────┐
│  User Favorites (5-50 종목)                           │
│   - LLM 카드 분석 (~$0.25/회)                          │
│   - ontology와 별개 layer (단순 우선순위)             │
│   - User Universe = Reference Universe + 사용자 본 종목│
└──────────────────────────────────────────────────────┘
```

### 3.1 Tier 모델

```
Tier 1 (~900) — Reference Universe core. ontology cross-match 영역
   KOSPI 200 + KOSDAQ 200 + S&P 500 + sector quota 보장

Tier 2 — 사용자가 favorite 등록 또는 카드 view한 종목
   자동 universe 편입 + 그 종목 ontology peer도 1-hop neighbor 자동 Tier 2 추가

Tier 3 — KR/US 나머지 모든 종목 메타
   ontology cross-match 안 함. 검색 시 hit 가능, 관심 등록되면 Tier 2 승격
```

### 3.2 Frontend 노출 limit

- **카드 RelationsSection (compact 1-line)**: top 3 관계 (strength × recency desc)
- **카드 RelationsSection (expanded 표)**: top 10
- **P3 Stock Universe graph**: 1-hop neighborhood (~30-50 노드), zoom으로 확장
- **검색**: universe pool 우선, miss 시 Tier 3 fallback

---

## 4. Schema 확장 — `stock_relations`

기존 P1 schema:
```sql
id, from_stock_id, to_target, to_kind, relation_type,
strength, notes, source, discovered_at, refreshed_at
```

P1.5에서 추가됨:
```sql
-- alembic a68d8f268caf
UNIQUE(from_stock_id, to_target, relation_type, source)
```

**P1.6에서 추가할 컬럼**:
```sql
ALTER TABLE stock_relations
  ADD COLUMN signal_direction VARCHAR(20) DEFAULT 'positive',
  -- positive: A 호재 → B 호재 (peer/supply 일반)
  -- negative: 둘 다 같은 충격 받음 (regulatory_link)
  -- inverse: A 호재 → B 악재 (competitor / zero-sum)

  ADD COLUMN confidence FLOAT DEFAULT 0.5,
  -- 데이터 신뢰도 (auto_sector_match 0.5 / disclosure_explicit 0.95 / llm_news 0.7)
  -- strength와 분리 — strength는 관계 강도, confidence는 데이터 출처 품질

  ADD COLUMN valid_from DATE,
  ADD COLUMN valid_until DATE,
  ADD COLUMN is_active BOOLEAN DEFAULT TRUE,
  -- 계약 만료 시 is_active=false, historical archive로 유지

  ADD COLUMN metadata JSONB;
  -- 계약 액수 / 기간 / source URL / 추출 시점 등
```

**relation_type CHECK 확장**:
```
peer / supply_upstream / supply_downstream / group / theme / macro /
competitor / contract_supplier / contract_customer / complementary /
regulatory_link
```

---

## 5. Universe Seed — Selection Plan

### 5.1 Source

| 시장 | source | selection 방식 | refresh |
|---|---|---|---|
| KR KOSPI | `dartlab.listing()` → KOSPI 시장 필터 → 시총 desc → top 200 | 시총 + 시장 분류 | nightly cron |
| KR KOSDAQ | 동일 → KOSDAQ → top 200 | 동일 | 동일 |
| US S&P 500 | wikipedia `List of S&P 500 companies` HTML table → tickers | index membership | 분기 refresh |

### 5.2 Sector Quota — 균등 분포 보장

단순 시총 top은 IT/Financial 편향. GICS 11 sector마다 **minimum 30종목 보장**:

```python
def select_universe(target_size, min_per_sector=30):
    by_sector = group_by(all_stocks, lambda s: s.sector)
    selected = set()
    for sector, stocks in by_sector.items():
        top = sorted(stocks, key=lambda s: -s.market_cap)[:min_per_sector]
        selected.update(top)
    # Fill remaining with global top market_cap not yet selected
    ...
    return selected
```

### 5.3 Edge cases

| 케이스 | 처리 |
|---|---|
| 신규 상장 | nightly cron 자동 편입 |
| 상장폐지 / 거래정지 | `is_delisted=true` 플래그, row 유지 (historical relation 보존) |
| 합병 / 분할 | 메타 update + ontology relations migration script |
| 사용자 검색 Tier 3 종목 | 자동 universe 편입 (Tier 3 → Tier 2 승격) |
| 시총 급변 | nightly refresh가 reflect (top N 진입/탈락) |

---

## 6. Relation Extraction Pipeline

### 6.1 Source 5가지

| Source | relation_type | 신뢰도 | 우리 위치 |
|---|---|---|---|
| Universe sector match | `peer` | 0.5 | P1.5 onto_hook 확장 |
| dartlab industry_graph (KR) | `supply_upstream/downstream` | 0.7 | P1.5에 fetch_industry_graph 통합됨 |
| DART 공시 (KR) | `contract_supplier/customer` | 0.95 | `collectors/disclosures.py` + dartlab `companyFilings` 통합. **본문 LLM RAG 신규 작업** |
| SEC 8-K Item 1.01 (US) | 동일 | 0.95 | SEC EDGAR adapter 확장 (filings filter + 본문 fetch). **본문 LLM RAG 신규** |
| 뉴스 본문 (KR/US) | `competitor` (inverse signal) / `contract_*` 보조 | 0.7 | `collectors/news.py` 통합됨. **본문 LLM RAG 신규** |
| Web search (Tavily) | `complementary` / `regulatory_link` | 0.5 | P1.5 통합. **상세 추출 신규** |
| 가격 시계열 상관관계 | `competitor` 후보 검증 (correlation < -0.3) | 0.7 | **신규 산출 함수** |

### 6.2 LLM RAG Pipeline

```
Trigger: nightly cron
   │
   ├─ 1. 최근 7일 disclosure / news / web search 본문 수집
   │     (이미 collectors가 함)
   │
   ├─ 2. 본문 chunk → LLM prompt:
   │     "이 텍스트에서 universe 안 ticker pair 사이의
   │      contract / competitor / complementary 관계 추출.
   │      JSON: {from_ticker, to_ticker, relation_type,
   │             signal_direction, strength, value_krw,
   │             term_months, source_url, confidence}"
   │
   ├─ 3. Validation:
   │     - from/to ticker ∈ Reference Universe
   │     - dedup (같은 source URL 같은 pair)
   │     - confidence >= threshold (0.6 자동, 미만 review queue)
   │
   ├─ 4. Persist: stock_relations row + metadata에
   │     source_url / value / term / extracted_at
   │
   └─ 5. ON CONFLICT (from, to, type, source) DO UPDATE
         strength = avg(old, new), refreshed_at = now()
```

### 6.3 비용 — gpt-5-mini-tier (cheap)

- 일 universe ~900 종목 × 평균 새 공시 0.5건 = ~450 disclosure
- 평균 본문 ~5K token × 450 = 2.25M token/day
- ~$0.15/M token = **$0.34/day = ~$10/month**
- 가족용 budget 안 (메인 spec §17 분석 비용 budget $5/day과 별개)

### 6.4 Manual curation 영구 deferred 유지

자동 path가 메인이라 manual curation UI 불요. 메인 spec §15 결정 그대로.

단 review queue (confidence < 0.6) 자동 추출 결과는 admin 페이지에 노출만 가능 (수정 X). P1.9 또는 후속.

---

## 7. Frontend 발견 UX

### 7.1 카드 RelationsSection — `★` 발견 배지

```
종목         유형              방향     강도   신뢰   변동
SK하이닉스    peer             →       90%   95%   +2.8%   ← 즐겨찾기
한미반도체★  contract_customer  →       85%   90%   -1.1%   ← ontology 발견
DB하이텍★   peer             →       70%   95%   +0.5%
마이크론      competitor       ↑반대   78%   80%   +1.5%   ← inverse signal
ASML★       contract_supplier →       70%   90%   +0.3%
```

- ★ 배지 = 사용자 즐겨찾기 X, ontology connected
- 클릭 → 그 종목 카드로 navigate
- 즐겨찾기 추가 또는 카드 분석 trigger 선택 가능
- ↑반대 표시 = `signal_direction=inverse` (zero-sum)

### 7.2 P3 Stock Universe Graph

react-force-graph-2d로 ontology 전체 navigate (P3 마일스톤):
- **노드** = Reference Universe 종목 + 매크로 factor. ★ = 즐겨찾기
- **엣지** = relation_type별 색상 (peer 청 / supply 보라 / theme 황 / macro 회 / competitor 적)
- **엣지 부호** = signal_direction (positive 실선 / inverse 빨간 점선)
- **클러스터** = sector/industry → 자연 emerge (force-directed)
- 클릭 → 카드 이동 + 즐겨찾기 추가
- 1-hop neighborhood 우선 표시, zoom으로 확장

---

## 8. Migration / Rollout

### Phase A — Universe Seed (P1.7)
1. `Stock` 모델에 `tier` / `is_reference` / `market_cap` / `liquidity` / `is_delisted` 컬럼 추가 (alembic)
2. `backend/scripts/seed_universe.py` — KOSPI/KOSDAQ/S&P 500 자동 seed
3. nightly cron in scheduler
4. PR: "feat: reference universe seed (P1.7)"

### Phase B — Schema 확장 (P1.6 v0)
1. alembic — signal_direction / confidence / valid_period / metadata 컬럼 추가
2. relation_type CHECK 확장 (5 추가)
3. P1.5 onto_hook 양방향 fix + sector_match 자동 universe-wide cross-match
4. PR: "feat: ontology schema expansion + auto sector match (P1.6 v0)"

### Phase C — DART 공시 LLM RAG (P1.6 v1)
1. `services/ontology/extractor.py` 신규 — 본문 chunk + LLM prompt
2. `services/ontology/validator.py` — universe 매칭 + dedup
3. nightly cron 통합
4. PR: "feat: DART contract extraction (P1.6 v1)"

### Phase D — SEC 8-K LLM RAG (P1.6 v2)
1. SEC EDGAR adapter `fetch_8k_filings` 확장
2. 본문 fetch + LLM RAG
3. PR: "feat: SEC 8-K contract extraction (P1.6 v2)"

### Phase E — 뉴스 LLM RAG (P1.6 v3)
1. 뉴스 본문 chunk + competitor / inverse signal 추출
2. 가격 상관관계 검증 함수
3. PR: "feat: news + correlation-based competitor extraction (P1.6 v3)"

### Phase F — Web search 보강 (P1.6 v4)
1. complementary / regulatory_link
2. PR: "feat: web search ontology extraction (P1.6 v4)"

---

## 9. LangGraph / RAG 미래 도입 Trigger

지금은 plain Python async + 직접 ReAct loop. 미래 도입 trigger:

| 도구 | 도입 시점 | Migration 비용 |
|---|---|---|
| **RAG (pgvector)** | 공시 본문 너무 길어 chunking + retrieval 필요 (e.g., 10-K 100K+ token) | 낮음 — extractor 사이 retrieval layer 끼움. PostgreSQL 17 `pgvector` extension만 추가 |
| **LangGraph multi-agent** | research agent multi-step branching 복잡해질 때 / specialist agent 분리 가치 명확해질 때 | 중간 — pipeline 함수 단위 분리되어 있어 노드 1:1 migration. spec §4 변경 필요 |
| **own vector store (LanceDB / Qdrant)** | universe ≥ 5K + relations ≥ 100K row → query 부담 시 | 별도 infra 도입 |

Migration 친화적 보장 (현재 architecture):
- LLM adapter 추상화 (AzureOpenAIAdapter) — LangChain wrapper로 감쌈 가능
- Pipeline 함수 단위 분리 — LangGraph node 1:1
- Pydantic schema 통일 — state graph state 타입 그대로
- External adapter layer — tool 추상화 그대로

---

## 10. Acceptance Criteria

P1.7 + P1.6 끝났을 때:

- [ ] Reference Universe ≥ 800 종목 seed 완료, GICS 11 sector 모두 ≥ 30종목
- [ ] Stock 모델 `tier` / `is_reference` / `market_cap` / `is_delisted` 컬럼
- [ ] alembic migration: stock_relations + 5 컬럼 (signal_direction / confidence / valid_period / metadata)
- [ ] relation_type 11 type 모두 CHECK 통과 (peer/supply_*/group/theme/macro/competitor/contract_*/complementary/regulatory_link)
- [ ] sector_match auto cross-match: universe-wide peer 등록 ≥ 5,000 row
- [ ] DART 공시 LLM RAG: 7일 backfill 후 contract_supplier/customer ≥ 10 row
- [ ] SEC 8-K LLM RAG: 동일
- [ ] 뉴스 LLM RAG: competitor / inverse signal ≥ 20 row
- [ ] Frontend ★ 배지 + signal_direction 시각화 (카드 RelationsSection)
- [ ] 005930 카드 열어보면 IT/반도체 sector peer 자동 등록되어 표시
- [ ] LLM RAG 일 비용 < $0.50 측정
- [ ] Manual curation UI 미구현 (영구 deferred 유지)

---

## 11. Out of Scope

- Manual curation UI — 영구 deferred (자동 추출이 메인)
- Sector ETF holdings 기반 추가 universe — v2.1 이후
- Talent flow / IP citation 기반 relation — v3+
- 실시간 ontology 갱신 (현재는 nightly) — v2.1 옵션
- 사용자별 personalized ontology weight — 영구 deferred
- LangGraph 도입 — 미래 trigger 충족 시
- RAG (pgvector) — 미래 trigger 충족 시

---

## 12. References

- 메인 spec: `docs/superpowers/specs/2026-04-28-ontology-aware-stock-card-design.md`
- P1.5 어댑터 spec: `docs/superpowers/specs/2026-04-29-external-data-adapters.md`
- 메모리: `~/.claude/projects/.../memory/feedback_ontology_product_model.md`
- 후속 plans (작성 예정):
  - `docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md`
  - `docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md`
