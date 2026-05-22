# Daily Analysis Archive + Event Markers Design

## Goal

StockInsight should remember why a stock moved over time. The latest card remains the primary decision surface, but previous daily analyses must stay visible as a stock-specific memory layer and as event markers on the price chart.

## Product Behavior

- The current card shows today's best decision.
- Historical daily cards become a compact "analysis history" timeline.
- The price chart shows event markers from previous analyses: price move causes, important news, and catalysts.
- When there is no fresh news, the UI should not feel empty. It should show that no new evidence changed the prior thesis and keep the most recent meaningful drivers visible.

## Architecture

Phase 1 reuses existing `analyses.card_data` JSONB rows. No schema migration is needed.

Backend adds two read-only endpoints:

- `GET /api/stocks/{ticker}/card/history`
- `GET /api/stocks/{ticker}/events`

Frontend adds:

- chart event markers in `HeroChart`
- a compact event strip under the chart
- an analysis history section in the card body

## Event Rules

Markers are extracted from past cards in this order:

1. `recent_price_move` causes, dated by `biggest_move_date`, `evidence_date`, or analysis date
2. card `news` items, dated by `published_at`
3. `thesis.catalysts`, dated by `when` when a date is parseable

Events are deduplicated by `date + title + source_type`, sorted newest first, and capped by API `limit`.

## UX Rules

- Markers must be short enough to sit on a chart.
- The full reason appears in the event strip below the chart.
- Red means positive/upside, blue means negative/downside, gray means neutral/mixed.
- History should emphasize changes: stance, grade, key reason, and recent price move.

## Non-Goals

- No new DB event table in phase 1.
- No editable analyst journal in phase 1.
- No LLM regeneration for old cards in phase 1.
