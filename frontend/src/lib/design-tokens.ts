/**
 * Design tokens for v2 stock card.
 *
 * Spec: docs/superpowers/specs/2026-04-28-ontology-aware-stock-card-design.md §12
 * Plan: docs/superpowers/plans/2026-04-29-p2-frontend-card.md §6, §17
 *
 * Pattern: light/dark pairs of hex values. Components read via `useTheme()`
 * + `pick(token, mode)`. CSS custom-property wiring lives in sub-phase B/C.
 */

export type ThemeMode = "light" | "dark";

type LD<T> = { light: T; dark: T };

/** Pick the mode-specific slice of a light/dark token. */
export function pick<T>(token: LD<T>, mode: ThemeMode): T {
  return token[mode];
}

// ─── Verdict ────────────────────────────────────────────────────────────────
// BUY / WATCH / REJECT — header badge, at-a-glance, decision section
export const verdictTokens = {
  BUY: {
    light: { bg: "#e6f4ec", fg: "#0a8f3d", border: "#a8d8b8" },
    dark:  { bg: "#0e2818", fg: "#4ade80", border: "#1f4a2c" },
  },
  WATCH: {
    light: { bg: "#fdf6e3", fg: "#a06800", border: "#e6c97a" },
    dark:  { bg: "#2a1d05", fg: "#fbbf24", border: "#5a4a14" },
  },
  REJECT: {
    light: { bg: "#fce8e8", fg: "#c81e1e", border: "#f3a5a5" },
    dark:  { bg: "#2a0e0e", fg: "#f87171", border: "#5a2020" },
  },
} satisfies Record<"BUY" | "WATCH" | "REJECT", LD<{ bg: string; fg: string; border: string }>>;

// ─── Final Grade S/A/B/C/D ──────────────────────────────────────────────────
export const gradeTokens = {
  S: { light: "#7c3aed", dark: "#a78bfa" },
  A: { light: "#0a8f3d", dark: "#4ade80" },
  B: { light: "#0891b2", dark: "#22d3ee" },
  C: { light: "#a06800", dark: "#fbbf24" },
  D: { light: "#c81e1e", dark: "#f87171" },
} satisfies Record<"S" | "A" | "B" | "C" | "D", LD<string>>;

// ─── Surface (card / section / glance highlight / decision highlight) ───────
export const surfaceTokens = {
  card:     { light: "#ffffff", dark: "#0f0f14" },
  section:  { light: "#fafafa", dark: "#16161e" },
  glance:   { light: "#f5f0fe", dark: "#1e1838" },  // subtle purple — at-a-glance
  decision: { light: "#f0fdf4", dark: "#0a1f12" },  // green tint — decision section
  border:   { light: "#e5e5e9", dark: "#252530" },
  text:     { light: "#1a1a22", dark: "#e0e0e8" },
  textMuted:{ light: "#6b6b75", dark: "#9ca3af" },
} satisfies Record<string, LD<string>>;

// ─── Citation [n] badge ─────────────────────────────────────────────────────
export const citeTokens = {
  bg: { light: "#f0f4f8", dark: "#1a2030" },
  fg: { light: "#0066cc", dark: "#60a5fa" },
} satisfies Record<"bg" | "fg", LD<string>>;

// ─── Chart (lightweight-charts v5) — spec §12.3 ─────────────────────────────
export const chartTokens = {
  light: {
    close: "#0a8f3d", ma20: "#a06800",
    volumeUp: "#a8d8b8", volumeDown: "#f3a5a5",
    grid: "#ececef", text: "#1a1a22",
  },
  dark: {
    close: "#4ade80", ma20: "#fbbf24",
    volumeUp: "#1f4a2c", volumeDown: "#5a2020",
    grid: "#1a1a22", text: "#e0e0e8",
  },
} satisfies LD<{
  close: string; ma20: string;
  volumeUp: string; volumeDown: string;
  grid: string; text: string;
}>;

// ─── Relation type — peer/supply_*/group/theme/macro ────────────────────────
export const relationTokens = {
  peer:              { light: "#0891b2", dark: "#22d3ee" },
  supply_upstream:   { light: "#7c3aed", dark: "#a78bfa" },
  supply_downstream: { light: "#db2777", dark: "#f472b6" },
  group:             { light: "#0a8f3d", dark: "#4ade80" },
  theme:             { light: "#a06800", dark: "#fbbf24" },
  macro:             { light: "#475569", dark: "#94a3b8" },
} satisfies Record<
  "peer" | "supply_upstream" | "supply_downstream" | "group" | "theme" | "macro",
  LD<string>
>;

// ─── Font size system — plan §17.2 ──────────────────────────────────────────
// Mobile base 16 / desktop base 14. h1 stays large on both viewports.
// Use as Tailwind responsive: e.g. `text-[16px] md:text-[14px]` for body.
export const fontSize = {
  h1:       { mobile: 24, desktop: 28 },  // ticker, 가격
  h2:       { mobile: 20, desktop: 22 },  // 섹션 헤더
  h3:       { mobile: 18, desktop: 20 },  // sub-section
  body:     { mobile: 16, desktop: 14 },  // 본문
  caption:  { mobile: 14, desktop: 13 },  // 보조 텍스트
  citation: { mobile: 12, desktop: 12 },  // [n] 배지 — both viewports identical
} as const;

// ─── Breakpoints — plan §17.1 ───────────────────────────────────────────────
export const breakpoints = {
  mobile:  375,
  tablet:  768,
  desktop: 1024,
  wide:    1280,
} as const;

// ─── Touch target — plan §17.4 ──────────────────────────────────────────────
export const TOUCH_TARGET_MIN = 44;  // ≥44×44px on mobile interactive elements
