"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import {
  analyzeStock,
  fullRefreshStock,
  getStockCard,
  newsRefreshStock,
  priceRefreshStock,
  refreshStockCard,
} from "@/services/api";
import type { StockCard } from "@/types/card";

export type CardLoadState = "loading" | "analyzing" | "ready" | "error";

const POLL_INTERVAL_MS = 5000;
const POLL_MAX_ATTEMPTS = 18; // ~90s — typical analyze pipeline finishes in 30-60s

// Light refresh (price / news) polling — server-side overlay 가 즉시 fresh
// price_asof / news_latest_at 반환 보장하지만, sync_prices/sync_news background
// task 가 완료될 때까지 약간의 지연 (yfinance 1콜 + DB INSERT 평균 1-2s).
// 500ms 간격 최대 6회 (3s 예산) — 옛 인위 3s sleep 보다 평균 빠름 + worst-case 동일.
const LIGHT_POLL_INTERVAL_MS = 500;
const LIGHT_POLL_MAX_ATTEMPTS = 6;

async function pollUntilAdvanced(
  ticker: string,
  pickTimestamp: (c: StockCard) => string | null | undefined,
  prevValue: string | null | undefined,
): Promise<StockCard | null> {
  for (let i = 0; i < LIGHT_POLL_MAX_ATTEMPTS; i++) {
    await new Promise((r) => setTimeout(r, LIGHT_POLL_INTERVAL_MS));
    try {
      const c = await getStockCard(ticker);
      const next = pickTimestamp(c);
      // 새 값이 옛 값보다 advance 했거나, 옛 값이 null 이었는데 새 값 박힘 — done.
      if (next && next !== prevValue) {
        return c;
      }
    } catch {
      /* transient — keep polling */
    }
  }
  // budget 소진 — 그래도 최신 카드 1회 반환 시도 (적어도 React state 새 ref).
  try {
    return await getStockCard(ticker);
  } catch {
    return null;
  }
}

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
  refreshAll: () => Promise<void>;
  refreshPrice: () => Promise<void>;
  refreshNews: () => Promise<{ aiRefreshLikely: boolean } | null>;
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

  const refreshAll = useCallback(async () => {
    // 전체 새로고침 — backend 가 sync_prices + sync_news + sync_disclosures
    // 후 analyze() 무조건. LLM $0.25, 5분 cooldown. generated_at advance 까지
    // long poll (analyze 평균 30-60s).
    const prevGeneratedAt = cardRef.current?.generated_at;
    dispatch({ type: "analyzeStart" });
    try {
      await fullRefreshStock(ticker);
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
        if (!prevGeneratedAt || c.generated_at !== prevGeneratedAt) {
          dispatch({ type: "loadOk", card: c });
          return;
        }
      } catch {
        /* keep polling */
      }
    }
    dispatch({
      type: "loadErr",
      error: "전체 새로고침이 1분 30초 안에 끝나지 않았어요. 잠시 후 새로고침 해보세요.",
    });
  }, [ticker]);

  const refreshPrice = useCallback(async () => {
    // sync_prices 1개만 — 외부 API 1콜, 가볍게. server-side overlay 가 fresh
    // price_asof 즉시 반환하지만 backend background task 끝나기 전엔 옛 값.
    // 500ms × 6회 polling 으로 price_asof advance 감지하면 stop.
    const prevPriceAsof = cardRef.current?.price_asof;
    try {
      await priceRefreshStock(ticker);
    } catch (e) {
      console.warn("price_refresh:", e);
    }
    const c = await pollUntilAdvanced(ticker, (x) => x.price_asof, prevPriceAsof);
    if (c) dispatch({ type: "loadOk", card: c });
  }, [ticker]);

  const refreshNews = useCallback(async () => {
    // 뉴스+공시 sync. server-side overlay 가 news_latest_at fresh 보장.
    // Backend 가 새 뉴스 ≥ 1건이면 analyze() 자동 trigger — 그건 더 오래 걸려서
    // (30-60s LLM) 여기 light polling 으로 못 감지. 사용자에게는 일단
    // news_latest_at advance 시점에 success 표시하고, AI 의견은 generated_at
    // 비교로 후속 polling. Backend 응답의 `ai_refresh_likely` hint 반환해
    // UI 가 "AI 의견도 갱신 중" / "그대로" 즉시 표시 가능.
    const prevNewsLatest = cardRef.current?.news_latest_at;
    const prevGeneratedAt = cardRef.current?.generated_at;
    let aiRefreshLikely = false;
    try {
      const meta = await newsRefreshStock(ticker);
      aiRefreshLikely = !!meta.ai_refresh_likely;
    } catch (e) {
      console.warn("data_refresh:", e);
    }
    const c1 = await pollUntilAdvanced(ticker, (x) => x.news_latest_at, prevNewsLatest);
    if (c1) dispatch({ type: "loadOk", card: c1 });
    // Best-effort: AI 의견 자동 재생성 polling (longer budget). generated_at
    // advance 안 하면 (새 뉴스 0건 → backend 가 trigger 스킵) 그대로 끝.
    for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      try {
        const c2 = await getStockCard(ticker);
        if (prevGeneratedAt && c2.generated_at !== prevGeneratedAt) {
          dispatch({ type: "loadOk", card: c2 });
          return { aiRefreshLikely };
        }
      } catch {
        /* keep polling */
      }
    }
    return { aiRefreshLikely };
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
    refreshAll,
    refreshPrice,
    refreshNews,
    triggerAnalyze,
  };
}
