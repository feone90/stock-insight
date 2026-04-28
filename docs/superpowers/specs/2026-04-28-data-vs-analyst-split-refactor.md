# Refactor — Synthesizer / Data Layer Split

**Status:** Draft — pending plan-eng-review
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

```
[Stage 1: Research]
   research_agent → research_notes (free-form findings, gaps, source list)
                      │
                      ├──────────────┐
                      ▼              ▼
[Layer A: DataAssembler]    [Layer B: Analyst LLM]
  - get_indicators(ticker)    - INPUT: research + DataAssembler output
  - get_macro_context()       - LLM call (analyst_v1 persona)
  - get_fundamentals(ticker)  - OUTPUT: AnalystOutput (4 fields)
  - get_recent_news + classify    glance, thesis, relations_interp, decision
  - server stock metadata
                      │              │
                      ▼              ▼
              [Engine.compose(data, analyst, ticker) → StockCard]
                      │
                      ▼
                  [persist]
```

### 3.2 Schema split

```python
# Existing StockCard becomes a *composed* shape. The LLM never produces the
# top-level Pydantic shape — it produces just AnalystOutput.

class DataLayer(BaseModel):
    """All deterministic / external-sourced sections."""
    technical: TechMomentum
    macro: MacroContext
    fundamentals: Fundamentals
    news: list[NewsItem]
    raw_citations: list[Citation]  # data-source citations

class AnalystOutput(BaseModel):
    """The four LLM-produced sections only."""
    glance: GlanceVerdict
    thesis: Thesis
    relations: RelationsSummary  # peer descriptions = LLM judgment
    decision: Decision
    interp_citations: list[Citation]  # any new citations LLM introduces (rare)

# StockCard composes them at engine layer:
class StockCard(BaseModel):
    # identity (server-injected from DB)
    ticker, name_ko, name_en, market, sector, tags, price, change, change_pct, asof
    # analyst layer
    glance, thesis, relations, decision  ← from AnalystOutput
    # data layer
    technical, macro, fundamentals, news  ← from DataLayer
    # merged
    citations  ← (data + analyst, deduped, [n] re-numbered)
    # meta
    analysis_id, generated_at, persona_version, schema_version, refresh_state
```

### 3.3 Citation merging

Each layer produces its own `Citation` list. The engine:
1. Collects DataLayer citations first (1, 2, 3, ...)
2. Appends AnalystOutput citations (continue numbering)
3. Re-points any inline `[n]` references in AnalystOutput strings to the merged numbering (search/replace)
4. Final list goes into `StockCard.citations`

Easier alternative: each layer uses **string-prefixed IDs** (e.g., `D-1`, `D-2`, `A-1`) and frontend renders as-is. Decision deferred to `plan-eng-review` — both are valid.

---

## 4. File-by-file changes

### Modified
- `backend/app/schemas/card.py`
  - Add `DataLayer` and `AnalystOutput` Pydantic models.
  - `StockCard` keeps current shape (frontend contract unchanged) — composed at engine.
- `backend/app/services/analyst/synthesize.py`
  - Returns `AnalystOutput` (NOT `StockCard`).
  - Prompt drastically reduced: "produce ONLY 4 fields: glance/thesis/relations/decision".
  - No need to inject DB metadata here.
- `backend/app/services/analyst/engine.py`
  - Renamed orchestration: research → data fetch (parallel) → analyst → compose → persist.
  - `compose()` does merging, citation renumbering, identity injection, validation.

### Created
- `backend/app/services/analyst/data_layer.py`
  - `assemble_data_layer(ticker) -> DataLayer` — calls `get_indicators` + `get_macro_context` + `get_fundamentals` + recent news + maybe `llm_classify_news`.
  - Pure orchestration; no new LLM calls except the existing `llm_classify_news` for news labeling.
- `backend/tests/test_data_layer.py`
  - One test per data sub-fetch + an integration test for full assembly.

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
| < 30 days price history | `technical = None` or all-null fields; thesis can still produce, citations note "indicators unavailable" |
| Tavily key missing | `web_search` returns `{results: [], error: ...}`; research notes flag gap; analyst proceeds with reduced evidence |
| LLM returns malformed AnalystOutput | Retry once with stricter prompt; second fail = raise ValueError, persist last-good or stale-banner state |
| Citation [n] in analyst text doesn't resolve | Engine drops the bracket OR keeps and frontend shows "?" — TBD in eng review |
| LLM tries to output technical/macro/fundamentals | Ignored at compose step (server values win); LLM gets feedback in retry only if shape itself invalid |
| Same-day re-run | Engine upserts in `analyses` (existing behavior preserved) |
| Phase A v1 row exists | Not touched — only v2 rows have `card_data` populated |

---

## 7. Test plan

### Unit
- `test_data_layer.py::test_assemble_returns_full_data_layer_with_seeded_ticker`
- `test_data_layer.py::test_assemble_handles_missing_indicators_gracefully`
- `test_data_layer.py::test_assemble_handles_empty_news`
- `test_synthesizer.py` — update existing tests to expect `AnalystOutput` (4 fields), not `StockCard`.

### Integration
- `test_engine.py::test_compose_merges_data_and_analyst_into_stock_card`
- `test_engine.py::test_compose_renumbers_citations_correctly`
- `test_engine.py::test_compose_preserves_phase_a_v1_rows`

### Smoke (opt-in)
- `test_smoke_005930.py` — same assertions, but now LLM output is 1/2 size → expected reliability ≥ 90% on first call.

### Regression
- All 191 existing tests must pass unchanged.

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

## 10. Open questions for plan-eng-review

1. **Citation merging strategy** — global re-number vs prefix (D-/A-)? Trade-off: re-number is cleaner UI, prefix is robust to LLM drift.
2. **Should `relations` stay LLM or move to data layer?** Strength values come from cache (data), but interpretation/peer-strength comparison needs judgment. Currently splitting: structure from data, narrative from LLM.
3. **Parallelism** — should DataAssembler fetches run in `asyncio.gather`? Each is a small DB query; serial might be fine. Premature opt?
4. **News classification** — `llm_classify_news` is an LLM call inside the data layer. Is that "data" or "LLM"? It's deterministic-ish (low-temp categorical labels). Place in data layer for now.
5. **Error in DataAssembler**: if `get_indicators` fails (DB issue), do we fail the whole analysis or proceed with `technical: None`? Currently lean toward "proceed with null section + research_notes records the gap".
6. **`AnalystOutput` validation strictness** — keep `min_length=3` for supports? Yes, but maybe move that constraint into a per-attempt prompt-side check so the LLM knows to retry itself. Pydantic validation at the outer layer can stay strict.

---

## 11. Acceptance criteria for refactor PR

- [ ] All 191 existing tests pass unchanged.
- [ ] New `test_data_layer.py` ≥ 3 tests, all green.
- [ ] `test_synthesizer.py` updated to expect `AnalystOutput`, all green.
- [ ] `test_engine.py` updated for new compose flow, all green.
- [ ] Smoke test passes for 005930 on first attempt without retry.
- [ ] Smoke test passes for 1 US ticker (e.g., AAPL) on first attempt — cross-ticker validation.
- [ ] Synthesizer prompt size measurably smaller (logged).
- [ ] No regression in Phase A chat (`/chat` endpoint still works).
- [ ] Frontend contract (`/api/stocks/{ticker}/card` response shape) unchanged from external POV.
- [ ] persona_version stays `analyst_v1`; persona prompt updated to focus on 4 sections.

---

## 12. Out of scope

- Modular per-section synthesis (4 separate LLM calls). Would help further but adds orchestration complexity. Reserve for v2.1 if 1-call still proves unreliable.
- Frontend changes — Plan 2 territory.
- Eval harness expansion — Plan 5 territory.
- Switching to Foundry's `response_format: json_schema` strict mode — needs investigation whether Foundry supports it. Reserve for follow-up.
