"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
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

  // refresh polling 이 옛 카드를 새 카드로 오판하지 않게, 현재 카드의
  // generated_at 을 ref 로 추적. backend 가 background 로 재분석하는 동안
  // 첫 200 응답은 옛 row 그대로 — 옛 generated_at 과 같으면 계속 polling.
  const cardRef = useRef<StockCard | null>(null);
  useEffect(() => {
    cardRef.current = state.card;
  }, [state.card]);

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
    const prevGeneratedAt = cardRef.current?.generated_at;
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
        // 옛 카드면(같은 generated_at) backend 가 아직 새 row 안 만든 상태 —
        // 계속 polling. 그래야 사용자 화면의 "마지막 분석 N분 전"이 정말 새
        // 시각으로 갱신된다.
        if (!prevGeneratedAt || c.generated_at !== prevGeneratedAt) {
          dispatch({ type: "loadOk", card: c });
          return;
        }
      } catch {
        // 404 / 일시 에러 가능 — 계속 polling.
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
