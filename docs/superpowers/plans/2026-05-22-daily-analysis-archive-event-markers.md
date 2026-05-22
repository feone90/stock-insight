# Daily Analysis Archive + Event Markers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show prior daily analysis memory and explain historical price moves with chart event markers.

**Architecture:** Reuse `analyses.card_data` JSONB snapshots. Add pure backend extraction helpers, expose read-only API routes, then render markers and a compact history timeline on the stock card.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Next.js 16, React 19, lightweight-charts 5.1.

---

### Task 1: Backend Schemas And Extraction

**Files:**
- Create: `backend/app/schemas/card_history.py`
- Create: `backend/app/services/analyst/history.py`
- Test: `backend/tests/test_card_history.py`

- [ ] Define response models for history rows and event markers.
- [ ] Add pure extraction helpers that accept `Analysis` rows.
- [ ] Cover price move, news, catalysts, dedupe, and sorting with unit tests.

### Task 2: Backend API Routes

**Files:**
- Modify: `backend/app/api/cards.py`

- [ ] Add `GET /{ticker}/card/history`.
- [ ] Add `GET /{ticker}/events`.
- [ ] Query latest v2 daily analysis rows and pass them through the extraction helpers.

### Task 3: Frontend API And Types

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/card.ts`

- [ ] Add TypeScript types matching backend response models.
- [ ] Add `getAnalysisHistory()` and `getStockEventMarkers()`.

### Task 4: Chart Event Markers

**Files:**
- Modify: `frontend/src/components/stock-v2/hero-chart.tsx`

- [ ] Fetch event markers for the selected chart window.
- [ ] Render lightweight-charts series markers.
- [ ] Show a compact event strip below the chart.

### Task 5: Analysis History Section

**Files:**
- Create: `frontend/src/components/stock-v2/analysis-history-section.tsx`
- Modify: `frontend/src/components/stock-v2/card-shell.tsx`

- [ ] Fetch card history for the ticker.
- [ ] Render a compact timeline of prior daily decisions.
- [ ] Include empty state that says there is no previous analysis yet.

### Task 6: Verification And Deploy

**Files:**
- All modified files

- [ ] Run backend focused tests.
- [ ] Run frontend `npx tsc --noEmit`.
- [ ] Run frontend `npm run build`.
- [ ] Commit and push `main`.
- [ ] Verify production URL returns HTTP 200.
