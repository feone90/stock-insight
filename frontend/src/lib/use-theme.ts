"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import type { ThemeMode } from "./design-tokens";

const STORAGE_KEY = "stockinsight-theme";

/**
 * useTheme — system preference + localStorage override.
 *
 * Uses `useSyncExternalStore` so the React 19 lint rule against
 * setState-in-effect is satisfied: localStorage and `prefers-color-scheme`
 * are external systems, not React state.
 *
 * Adds the `.dark` class on `<html>` so Tailwind's dark variant works.
 *
 * Spec §12.2 (모드 전환). Plan §6.
 */
export function useTheme(): {
  mode: ThemeMode;
  toggle: () => void;
  setMode: (m: ThemeMode) => void;
} {
  const mode = useSyncExternalStore(_subscribe, _getSnapshot, _getServerSnapshot);

  // Reflect mode to <html class="dark"> for Tailwind. Effect only touches
  // the DOM (no setState) → not blocked by the lint rule.
  useEffect(() => {
    const root = document.documentElement;
    if (mode === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
  }, [mode]);

  const setMode = useCallback((m: ThemeMode) => _setMode(m), []);
  const toggle = useCallback(() => _setMode(mode === "dark" ? "light" : "dark"), [mode]);

  return { mode, toggle, setMode };
}

// ─── Internal: external-store wiring ────────────────────────────────────────

function _getSnapshot(): ThemeMode {
  if (typeof window === "undefined") return "dark";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function _getServerSnapshot(): ThemeMode {
  return "dark";
}

function _subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) callback();
  };
  mql.addEventListener("change", callback);
  window.addEventListener("storage", onStorage);
  return () => {
    mql.removeEventListener("change", callback);
    window.removeEventListener("storage", onStorage);
  };
}

function _setMode(next: ThemeMode): void {
  window.localStorage.setItem(STORAGE_KEY, next);
  // Notify same-tab subscribers (the native `storage` event only fires across tabs).
  window.dispatchEvent(
    new StorageEvent("storage", { key: STORAGE_KEY, newValue: next }),
  );
}
