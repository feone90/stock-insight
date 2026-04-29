# Refactor — Synthesizer / Data Layer Split

**Status:** Reviewed (plan-eng-review applied) — ready to implement
**Date:** 2026-04-28
**Branch:** `feat/v2-backend-engine`
**Parent spec:** `docs/superpowers/specs/2026-04-28-ontology-aware-stock-card-design.md` (commit `8e2f4a6`)
**Trigger:** P1 smoke test failed schema validation — synthesizer LLM was producing partial output across 8 sections. Root cause: monolithic generation that conflates deterministic data with analyst judgment.

---

## 1. Problem

The current `run_synthesize(ticker, research)` builds a **single LLM call** that must emit all 8 StockCard sections in one JSON object: `glance`, `thesis`, `technical`, `relations`, `news`, `macro`, `fundamentals`, `decision` (+ `citations` pool).

But only 4 of those sections are actually analyst judgment. The other 4 are data echoing:
- `technical` — pure indicator math (RSI/MA/RVOL/ATR/CMF/OBV) — already computed by `get_indicators` in Stage 1.
- `macro` — VIX/USD/KRW/sector ETFs — `get_macro_context` already returns the values.
- `fundamentals` — PER/PBR/시총/배당 — already in `Financial` table.
- `news` — title/url/source already in DB; only `impact` label is analyst-flavored.

The LLM is asked to copy these into the output JSON instead of letting the server fill them. Result:
- Output token budget consumed by data restatement → analytical sections become thin or missing.
- Smoke test: 36 validation errors, multiple required sections empty.
- Persona contract (≥3 supports, ≥2 opposes, BULL/BASE/BEAR scenarios) under-enforced because LLM is rushing to emit everything.

This is an **architecture mistake** in the parent spec, not a tuning problem. No amount of prompt iteration fixes it cleanly — it always re-emerges with new tickers / new contexts.

---

## 2. Design Principle (locked)

For every field in `StockCard`, ask: **who produces this — code, LLM, or external API?**

| Origin | Examples |
|--------|----------|
| Code (deterministic) | RSI math, MA stack, β coefficient, today's price-change %, age of latest news |
| LLM (judgment) | core_thesis, support/oppose claims, scenario probabilities, decision rationale, peer interpretation |
| External (raw) | News titles + URLs, macro factor values, fundamental ratios |

LLM is **only invoked for judgment**. Data is plumbed through.

---

## 3. New Architecture

### 3.1 Pipeline

Two parallel branches after research, joined at compose. The analyst does NOT
read DataAssembler output directly — it reads research notes (which already
include indicator/news values via Stage 1 tool calls). Compose is the
single source of truth for which numbers land in the final card.

```
[Stage 1: Research]
   research_agent → research_notes (free-form findings, gaps, source list)
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
  [Layer A: DataAssembler]  [Layer B: Analyst LLM]
  asyncio.gather(            INPUT: research_notes only
    get_indicators,          (NOT data layer output)
    get_macro_context,       OUTPUT: AnalystOutput
    fetch_fundamentals,        - glance
    fetch_recent_news_         - thesis
    + classify,                - relations_narrative (one_line + notes_by_target)
    fetch_relations_data       - decision
  )                            - interp_citations (rare, optional)
  OUTPUT: DataLayer
    - technical
    - macro
    - fundamentals
    - news
    - relations_data (list[Relation], cache+DB)
    - data_citations
            │                   │
            └─────────┬─────────┘
                      ▼
        [Engine.compose(data, analyst, ticker) → StockCard]
        - server-injects identity (ticker, name, market, price, asof)
        - merges relations_data + relations_narrative.notes_by_target
        - re-numbers citations globally (data first, then analyst-introduced)
        - re-maps Claim.citations: list[int] field-level (no prose substitution)
        - validates against StockCard (strict)
                      │
                      ▼
                  [persist]
```

### 3.2 Schema split

Relations is split between layers — structure is data, narrative is analyst.

```python
# Existing StockCard becomes a *composed* shape. The LLM never produces the
# top-level Pydantic shape — it produces just AnalystOutput.

class DataLayer(BaseModel):
    """All deterministic / external-sourced sections."""
    technical: TechMomentum
    macro: MacroContext
    fundamentals: Fundamentals
    news: list[NewsItem]
    relations_data: list[Relation]   # target_ticker, name, type, strength,
                                     # today_change_pct — all from cache+DB
    data_citations: list[Citation]   # data-source citations (db/market_data/
                                     # news/disclosure/web/curated_relation)


class RelationsNarrative(BaseModel):
    """Analyst-only commentary that overlays the structured relations_data."""
    one_line: str
    notes_by_target: dict[str, str]  # {"000660": "HBM 동조 수혜", ...}
    citations: list[int]


class AnalystOutput(BaseModel):
    """The LLM-produced judgment fields only — no data echoing."""
    glance: GlanceVerdict
    thesis: Thesis
    relations_narrative: RelationsNarrative   # NOT the full RelationsSummary
    decision: Decision
    interp_citations: list[Citation] = []     # rare: LLM introduces a new web
                                              # source not already in research

# StockCard composes them at engine layer (frontend contract unchanged):
class StockCard(BaseModel):
    # identity — server-injected from DB at compose
    ticker, name_ko, name_en, market, sector, tags, price, change, change_pct, asof
    # analyst layer
    glance, thesis, decision  ← from AnalystOutput
    # data layer
    technical, macro, fundamentals, news  ← from DataLayer
    # merged at compose:
    relations  ← RelationsSummary built from data.relations_data
                   + analyst.relations_narrative.{one_line, notes_by_target}
    # citations: data first, then analyst, deduped, globally re-numbered
    citations
    # meta
    analysis_id, generated_at, persona_version, schema_version, refresh_state
```

### 3.3 Citation merging — schema-level remap (NOT prose substitution)

The schema already separates citations from prose: `Claim.text` is plain
prose with no inline `[n]` markers; `Claim.citations: list[int]` is a
structured field of citation IDs. Same for every section's citations list.
Therefore citation merging is a pure ID remap, not a string-substitution problem.

Algorithm at compose:
1. Concatenate citation pools in order: `final = data.data_citations + analyst.interp_citations`.
2. Build remap: each citation gets a final ID from 1..N based on its position
   in `final`. Save mapping `old_id → new_id`. Data citations first (their old
   IDs come from DataAssembler, typically 1..K), analyst citations renumber to
   K+1..K+M.
3. Walk every nested `citations: list[int]` field across the composed
   StockCard (Claim.citations, GlanceVerdict.citations, MacroContext.citations,
   etc.) and apply the remap.
4. Validate: every integer referenced in any `citations` list must appear in
   the final pool. If not, raise — engine returns 503 (compose error).

Decision: **global re-numbering chosen, prefix variant rejected.**
String prefixes (D-/A-) only become useful if the analyst emits inline
`[n]` in prose, which our schema explicitly avoids. So global integer IDs
are simpler, cleaner UI, no extra rendering logic.

---

## 4. File-by-file changes

### Modified
- `backend/app/schemas/card.py`
  - Add `DataLayer`, `AnalystOutput`, `RelationsNarrative` Pydantic models.
  - `StockCard` keeps current shape (frontend contract unchanged).
- `backend/app/services/analyst/__init__.py`
  - Add common `get_analyst_adapter()` factory. Replaces duplicated `_adapter()`
    helpers in research.py / synthesize.py / tools.py / data_layer.py (DRY).
- `backend/app/services/analyst/synthesize.py`
  - Returns `AnalystOutput` (NOT `StockCard`).
  - Prompt focused on 4 LLM fields: glance, thesis, relations_narrative, decision.
  - **Remove `_fetch_stock_metadata`** — moved into `data_layer.py` / `engine.compose`.
  - Use shared `get_analyst_adapter()`.
- `backend/app/services/analyst/research.py` and `tools.py`
  - Use shared `get_analyst_adapter()`.
- `backend/app/services/analyst/engine.py`
  - Rewrite `analyze(ticker)`:
    1. `research = await run_research(ticker)`
    2. `data, analyst = await asyncio.gather(assemble_data_layer(ticker), run_synthesize(ticker, research))`
    3. `card = compose(ticker, data, analyst)`
    4. persist (existing upsert logic).
  - New `compose(ticker, data, analyst) -> StockCard` does merging, citation
    remap, identity injection, validation.

### Created
- `backend/app/services/analyst/data_layer.py`
  - `assemble_data_layer(ticker) -> DataLayer` — `asyncio.gather` over:
    - `get_indicators` (existing tool)
    - `get_macro_context` (existing tool)
    - `_fetch_fundamentals` (new helper — Financial table query)
    - `_fetch_recent_news` (existing tool) + `llm_classify_news` (existing)
    - `_fetch_relations_data` (existing `get_relations` for all types)
  - Per-section graceful degrade: if a sub-fetch fails, that section becomes
    None/empty + warning log; compose proceeds.
  - Background-trigger `llm_discover_relations` if relation cache `refreshed_at`
    older than 7 days (fire-and-forget; current analysis uses stale cache).
- `backend/tests/test_data_layer.py`

### Deleted
- None. Existing tools (`get_indicators`, `get_macro_context`, etc.) all stay.

---

## 5. Schema decisions

- `DataLayer.technical` etc. stay nested with their existing field shape — no breaking change.
- `AnalystOutput` is **new** but composes existing types. No frontend impact (only backend internal).
- Output frontend contract (`/api/stocks/{ticker}/card` JSON) **unchanged** — same `StockCard` shape returned.
- Citations remain a flat list at `StockCard.citations`.

---

## 6. Edge cases & invariants

| Case | Behavior |
|------|----------|
| Stock not in DB | Fail-fast 404 from API; engine never invoked |
| **`stock.current_price <= 0` or 0 price-history rows** | **Fail-fast 422** at API; do NOT analyze. UI shows "데이터 수집 중". Avoids misleading 0원 cards |
| < 30 days price history (but price > 0) | `technical = None`; thesis still produces with citations noting "indicators unavailable" |
| Tavily key missing | `web_search` returns `{results: [], error: ...}`; research notes flag gap; analyst proceeds with reduced evidence |
| `stock_relations` cache stale (>7 days `refreshed_at`) | Use stale cache for current analysis; **fire-and-forget background refresh** via `llm_discover_relations`. Next analysis sees fresh cache |
| News with `published_at` > 14 days old | Filter out at data_layer; only include recent (configurable, default 14d) |
| LLM cites non-existent citation ID (e.g. references `[99]` but only 5 citations exist) | Compose raises; engine retries synthesize once. Second fail = stale cache fallback |
| LLM scenario probabilities don't sum to ~1.0 (tolerance 0.95–1.05) | Pydantic validator; retry once |
| LLM returns malformed AnalystOutput (other validation errors) | Retry once with stricter prompt; second fail = stale-banner state |
| LLM tries to override server fields (ticker/name/price) | Compose ignores — server fields injected last, win |
| LLM tries to output technical/macro/fundamentals despite prompt | Ignored at compose step (data layer wins) |
| Same-day re-run | Engine upserts in `analyses` (existing behavior preserved) |
| Phase A v1 row exists for same stock_id+date | Not touched — `WHERE schema_version='v2'` discriminator |
| **Concurrent analyze() calls for same ticker** | **`asyncio.Lock` per-ticker** (in-memory dict in engine.py). Second call awaits first. Single-process scope |
| Memory: research notes 30KB + data 10KB + analyst output 5KB | Within hand. Log warning if total > 200KB (signals research went off rails) |

---

## 7. Test plan

### Unit
- `test_data_layer.py`
  - `test_assemble_returns_full_data_layer_with_seeded_ticker` — happy path
  - `test_assemble_handles_missing_indicators_gracefully` — < 30 days history → technical=None, others populated
  - `test_assemble_handles_empty_news` — no news → news=[]
  - `test_assemble_handles_empty_macro` — no macro_factors rows → macro fields None
  - `test_assemble_skips_when_stock_not_found` — returns sentinel or raises clearly
  - `test_assemble_uses_asyncio_gather` — patch the underlying tools, assert all 5 awaited concurrently (timing-based or call-order assertion)
  - `test_assemble_triggers_relations_refresh_when_stale` — fire-and-forget bg task scheduled
- `test_synthesizer.py` — UPDATE existing tests:
  - All currently expect `StockCard` return — change to `AnalystOutput`.
  - Update mock LLM responses to omit data layer fields (only 4 LLM fields).

### Integration
- `test_engine.py`
  - `test_compose_merges_data_and_analyst_into_stock_card` — happy
  - `test_compose_renumbers_citations_globally` — old IDs from layers are remapped, all `Claim.citations: list[int]` reference final IDs
  - `test_compose_merges_relations_data_with_narrative` — Relation objects from data layer get `notes` from `relations_narrative.notes_by_target`
  - `test_compose_server_fields_win_over_llm` — LLM emits `ticker="WRONG"` → compose forces correct
  - `test_compose_preserves_phase_a_v1_rows` — REGRESSION CRITICAL
  - `test_compose_handles_same_day_upsert`
  - `test_analyze_uses_per_ticker_lock` — two concurrent analyze() calls for same ticker serialize

### Adversarial (LLM mis-output)
- `test_synthesizer_adversarial.py`
  - `test_llm_cites_nonexistent_id_triggers_retry`
  - `test_llm_scenario_probabilities_dont_sum_triggers_retry`
  - `test_llm_returns_too_few_supports_triggers_retry`
  - `test_llm_returns_garbage_json_after_retries_raises_value_error`

### Property-based (citation invariants)
- `test_compose_property.py` (use `hypothesis` lib if accessible, else manual fuzz)
  - For random valid (DataLayer, AnalystOutput) pairs: every `Claim.citations: list[int]` element exists in `StockCard.citations` final pool.
  - Citation IDs in final pool are 1..N contiguous (no gaps).
  - Total citations count == sum of input layer citations (no double-count).

### Smoke (opt-in `-m smoke`)
- `test_smoke_005930.py` — UPDATE assertions for new compose flow. Expected reliability ≥ 90% first attempt.
- `test_smoke_aapl.py` — NEW. Cross-ticker validation (US market).
- `test_smoke_low_data_ticker.py` — NEW. Pick a recent IPO or thinly-covered ticker → assert graceful degrade (technical=None, etc.) without raising.

### Regression
- All 191 existing tests must pass unchanged. Run full suite at PR time.

---

## 8. Migration / rollout

- Same branch (`feat/v2-backend-engine`) — refactor on top of existing 24 commits.
- No DB migration (card_data JSONB shape can hold the same final StockCard).
- Existing v2 rows in DB (if any from earlier smoke attempts) are simply overwritten on next analyze.
- Zero impact on Phase A chat (different code paths entirely).

---

## 9. Cost/perf expectations after refactor

| Metric | Before | After (expected) |
|--------|--------|-------------------|
| Synthesizer prompt size | ~30KB (research dump) | ~15–18KB (research + structured data summary, no echo demand) |
| Synthesizer output size | ~5–8KB (filling 8 sections) | ~2–3KB (4 sections) |
| LLM cost per analysis | ~$0.5–1.2 | ~$0.3–0.7 |
| Synthesizer wall time | ~40–60s | ~20–35s |
| Smoke pass rate (ticker 005930) | 0/N | ≥ 90% |

---

## 10. Open questions — resolved by plan-eng-review

| # | Question | Decision |
|---|----------|----------|
| 1 | Citation merging — global vs prefix | **Global re-number, schema-field remap.** Prose has no inline `[n]`, only `citations: list[int]` field. Pure ID remap, no string substitution |
| 2 | Relations LLM vs data | **Split.** `relations_data: list[Relation]` is data layer (structure from cache+DB); `relations_narrative` is analyst (one_line + notes_by_target overlay) |
| 3 | DataAssembler parallelism | **`asyncio.gather` over 5 fetches.** Concrete benefit on manual refresh latency |
| 4 | News classification placement | **Data layer.** Deterministic-ish categorical (low-temp); analyst should consume already-classified news |
| 5 | DataAssembler error handling | **Per-section graceful degrade.** Sub-fetch fail → that section None/empty + warning log. Compose proceeds. UI shows "데이터 부족" badge |
| 6 | `AnalystOutput` validation strictness | **Keep strict** (`min_length=3` supports, `==3` scenarios, etc.). Failure → retry once with stricter prompt. Second fail → stale-banner fallback or 503. Don't silently relax |

---

## 11. Acceptance criteria for refactor PR

- [ ] All 191 existing tests pass unchanged.
- [ ] New `test_data_layer.py` ≥ 7 tests, all green.
- [ ] `test_synthesizer.py` updated to expect `AnalystOutput`, all green.
- [ ] `test_synthesizer_adversarial.py` ≥ 4 tests, all green.
- [ ] `test_engine.py` updated for new compose flow ≥ 7 tests, all green.
- [ ] `test_compose_property.py` citation invariants ≥ 3 tests.
- [ ] Smoke `005930` passes first attempt without retry.
- [ ] Smoke `AAPL` (or another US ticker) passes — cross-ticker validation.
- [ ] Smoke low-data ticker — graceful degrade without raising.
- [ ] `_fetch_stock_metadata` removed from `synthesize.py`; replaced by `data_layer.py` + `engine.compose` server-injection.
- [ ] `RelationsSummary` composed from `data.relations_data` + `analyst.relations_narrative`.
- [ ] Common `get_analyst_adapter()` factory in `services/analyst/__init__.py`; duplicate `_adapter()` removed from research/synthesize/tools.
- [ ] `asyncio.Lock` per-ticker in `engine.py` for concurrent analyze().
- [ ] Synthesizer prompt size ≤ 18KB (logged + asserted in test).
- [ ] No regression in Phase A chat (`/chat` endpoint still works — explicit smoke).
- [ ] Frontend contract (`/api/stocks/{ticker}/card` response shape) unchanged.
- [ ] persona_version stays `analyst_v1`; prompt updated to focus on 4 fields.

---

## 12. Out of scope

- **Modular per-section synthesis** (4 separate LLM calls — one per analyst field).
  Single-call with 4 fields should be reliable. **Escalation trigger:** if smoke
  pass rate < 80% across 5 diverse tickers (KR mega-cap, KR small-cap, US
  mega-cap, US ETF, recent IPO), then v2.1 splits into per-section calls.
- Frontend changes — Plan 2 territory.
- Eval harness expansion (LLM-as-judge for citation accuracy, cycle awareness)
  — Plan 5 territory.
- Switching to Foundry's `response_format: json_schema` strict mode — needs
  investigation whether Foundry supports it. Reserve for follow-up after
  smoke-stable.
- **`hypothesis` library introduction** — if not already a dep, add only if
  property tests prove valuable; otherwise hand-fuzz.
