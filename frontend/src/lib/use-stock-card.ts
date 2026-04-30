"use client";

import { useCallback, useEffect, useReducer } from "react";
import { analyzeStock, getStockCard, refreshStockCard } from "@/services/api";
import type { StockCard } from "@/types/card";

export type CardLoadState = "loading" | "analyzing" | "ready" | "error";

const POLL_INTERVAL_MS = 5000;
const POLL_MAX_ATTEMPTS = 18; // ~90s — typical analyze pipeline finishes in 30-60s

interface State {
  card: StockCard | null;
  status: CardLoadState;
  error: string | null;
}

type Action =
  | { type: "loadStart" }
  | { type: "analyzeStart" }
  | { type: "loadOk"; card: StockCard }
  | { type: "loadErr"; error: string };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "loadStart":
      return { ...state, status: "loading", error: null };
    case "analyzeStart":
      return { ...state, status: "analyzing", error: null };
    case "loadOk":
      return { card: action.card, status: "ready", error: null };
    case "loadErr":
      return { ...state, status: "error", error: action.error };
  }
}

const initialState: State = { card: null, status: "loading", error: null };

/**
 * Fetch + manage a `StockCard` for `ticker`.
 *
 * Uses `useReducer` so async-resolved updates run via `dispatch` rather than
 * setState — this satisfies React 19's `react-hooks/set-state-in-effect` rule,
 * which blocks setState in effect callbacks. SWR/React Query is the proper
 * library answer; introduction is deferred to P5 polish.
 *
 * Plan §5 (data flow).
 */
export function useStockCard(ticker: string): {
  card: StockCard | null;
  state: CardLoadState;
  error: string | null;
  refresh: () => Promise<void>;
  triggerAnalyze: () => Promise<void>;
} {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: "loadStart" });
    getStockCard(ticker)
      .then((c) => {
        if (!cancelled) dispatch({ type: "loadOk", card: c });
      })
      .catch((e: unknown) => {
        if (!cancelled)
          dispatch({
            type: "loadErr",
            error: e instanceof Error ? e.message : String(e),
          });
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const refresh = useCallback(async () => {
    dispatch({ type: "analyzeStart" });
    try {
      // Backend returns `{status, ticker}` (background task), not a card.
      await refreshStockCard(ticker);
    } catch (e) {
      dispatch({
        type: "loadErr",
        error: e instanceof Error ? e.message : String(e),
      });
      return;
    }
    for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      try {
        const c = await getStockCard(ticker);
        dispatch({ type: "loadOk", card: c });
        return;
      } catch {
        // Old row may still be returned briefly — accept any non-error read.
      }
    }
    dispatch({
      type: "loadErr",
      error: "재분석이 1분 30초 안에 끝나지 않았어요. 잠시 후 새로고침 해보세요.",
    });
  }, [ticker]);

  const triggerAnalyze = useCallback(async () => {
    dispatch({ type: "analyzeStart" });
    try {
      await analyzeStock(ticker);
    } catch (e) {
      dispatch({
        type: "loadErr",
        error: e instanceof Error ? e.message : String(e),
      });
      return;
    }
    // Poll for completion. Backend creates the Analysis row only when the
    // pipeline finishes, so 200 from `getStockCard` means we're done.
    for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      try {
        const c = await getStockCard(ticker);
        dispatch({ type: "loadOk", card: c });
        return;
      } catch {
        // 404 expected while analysis is still running.
      }
    }
    dispatch({
      type: "loadErr",
      error: "분석이 1분 30초 안에 끝나지 않았어요. 잠시 후 새로고침 해보세요.",
    });
  }, [ticker]);

  return {
    card: state.card,
    state: state.status,
    error: state.error,
    refresh,
    triggerAnalyze,
  };
}
