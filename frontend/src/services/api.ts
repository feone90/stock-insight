import type { Stock, PriceRecord, Analysis } from "@/types/stock";
import type { StockCard } from "@/types/card";
import { getToken } from "@/services/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function userHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const user = localStorage.getItem("stockinsight.activeUser");
  if (!user) return {};
  // HTTP header는 ASCII만 허용 — 한국어 이름은 fetch가 TypeError로 거부.
  // encodeURIComponent로 ASCII 변환. backend가 unquote로 복원.
  return { "X-User-Id": encodeURIComponent(user) };
}

function combinedHeaders(): Record<string, string> {
  return { ...authHeaders(), ...userHeader() };
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: combinedHeaders(),
    signal,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

async function postJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: combinedHeaders(),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function searchStocks(
  query: string,
  signal?: AbortSignal
): Promise<Stock[]> {
  return fetchJson(`/api/stocks/search?q=${encodeURIComponent(query)}`, signal);
}

export async function getStock(ticker: string): Promise<Stock> {
  return fetchJson(`/api/stocks/${ticker}`);
}

export async function getStockPrices(
  ticker: string,
  days: number = 30
): Promise<PriceRecord[]> {
  return fetchJson(`/api/stocks/${ticker}/prices?days=${days}`);
}

export async function getAnalysis(
  ticker: string,
  period: string = "weekly"
): Promise<Analysis> {
  return fetchJson(`/api/stocks/${ticker}/analysis?period=${period}`);
}

export async function getFavorites(): Promise<Stock[]> {
  return fetchJson("/api/favorites");
}

export async function addFavorite(ticker: string): Promise<void> {
  await postJson(`/api/favorites/${ticker}`);
}

export async function getKnownUsers(): Promise<string[]> {
  return fetchJson("/api/favorites/users");
}

export async function removeFavorite(ticker: string): Promise<void> {
  // Codex review [medium]: add/list 는 combinedHeaders() 로 X-User-Id 보내는데
  // delete 만 authHeaders() 라 가족 user 별 favorite row 가 안 지워지고
  // default user 만 시도하다 fail. 멀티 user 경계 깨짐 → 같은 헤더로 통일.
  const res = await fetch(`${API_BASE}/api/favorites/${ticker}`, {
    method: "DELETE",
    headers: combinedHeaders(),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
}

export interface SyncResult {
  status: string;
  ticker?: string;
  synced: Record<string, number | boolean>;
  errors: string[];
}

export interface SyncAllResult {
  status: string;
  stocks_synced: string[];
  global_synced: boolean;
  total_synced: Record<string, number>;
  errors: string[];
}

export async function registerStock(ticker: string): Promise<Stock> {
  const res = await fetch(`${API_BASE}/api/stocks/register/${ticker}`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Register failed: ${res.status}`);
  return res.json();
}

export async function syncStock(ticker: string): Promise<SyncResult> {
  return postJson(`/api/admin/sync/stock/${ticker}`);
}

export async function syncAll(): Promise<SyncAllResult> {
  return postJson(`/api/admin/sync/all`);
}

// --- v2 Card API (P2) ---
// Backend router prefix is `/api/stocks` (not `/api/cards`) — see cards.py.

export async function getStockCard(ticker: string): Promise<StockCard> {
  return fetchJson(`/api/stocks/${ticker}/card`);
}

export async function refreshStockCard(ticker: string): Promise<StockCard> {
  return postJson(`/api/stocks/${ticker}/refresh`);
}

/**
 * 가격만 즉시 갱신 (sync_prices 1개 콜렉터). LLM 0, 외부 API 1회.
 * 차트·헤더 가격 즉시 fresh. 30s cooldown.
 */
export async function priceRefreshStock(
  ticker: string,
): Promise<{ status: string; ticker: string }> {
  return postJson(`/api/stocks/${ticker}/price_refresh`);
}

/**
 * 뉴스·공시 갱신 + 새 뉴스 ≥ 1건이면 AI narrative 자동 재생성. 2분 cooldown.
 * 가격은 별도 `/price_refresh`. 재무는 분기 단위라 야간 cron 처리.
 *
 * `ai_refresh_likely` — sync 전 시점에 last_card 기준 새 뉴스 count 가 ≥ 1
 * 이거나 첫 분석이면 true. background sync 후 count 가 0 이면 backend 가
 * 실제로 analyze 안 함 (낭비 방지). 즉 hint 일 뿐 — frontend 는 generated_at
 * advance polling 으로 actual 결과 확인.
 */
export interface NewsRefreshResult {
  status: string;
  ticker: string;
  auto_analyze_threshold_news: number;
  ai_refresh_likely: boolean;
}

export async function newsRefreshStock(
  ticker: string,
): Promise<NewsRefreshResult> {
  return postJson(`/api/stocks/${ticker}/data_refresh`);
}

/**
 * 전체 새로고침 — 가격 + 뉴스 + 공시 동기화 후 무조건 AI 재생성.
 * LLM 비용 $0.25, ~5-10초 소요. 5분 cooldown (`/refresh` 와 동일 정책).
 */
export async function fullRefreshStock(
  ticker: string,
): Promise<{ status: string; ticker: string }> {
  return postJson(`/api/stocks/${ticker}/full_refresh`);
}

export async function analyzeStock(
  ticker: string
): Promise<{ status: string; ticker: string }> {
  return postJson(`/api/stocks/${ticker}/analyze`);
}

// --- Ontology graph (P3) ---

import type { GraphPayload } from "@/types/ontology";

export async function getOntologyGraph(
  ticker: string,
  options: { depth?: number; cap?: number; sources?: string; minConfidence?: number } = {},
): Promise<GraphPayload> {
  const params = new URLSearchParams({ ticker });
  if (options.depth) params.set("depth", String(options.depth));
  if (options.cap) params.set("cap", String(options.cap));
  if (options.sources) params.set("sources", options.sources);
  if (options.minConfidence != null) params.set("min_confidence", String(options.minConfidence));
  return fetchJson(`/api/ontology/graph?${params.toString()}`);
}

// --- Chat API ---

import type { ChatMessage, SseEvent, ThreadSummary } from "@/types/chat";

export async function* streamChat(
  message: string,
  threadId: string | null,
  signal: AbortSignal
): AsyncGenerator<SseEvent, void, void> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`Chat API error: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = parseSseBlock(raw);
      if (event) yield event;
    }
  }
}

function parseSseBlock(block: string): SseEvent | null {
  const lines = block.split("\n");
  let eventName = "";
  let dataLine = "";
  for (const line of lines) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
  }
  if (!eventName || !dataLine) return null;
  try {
    const data = JSON.parse(dataLine);
    return { event: eventName, data } as SseEvent;
  } catch {
    return null;
  }
}

export async function listThreads(): Promise<ThreadSummary[]> {
  const res = await fetchJson<{ threads: ThreadSummary[] }>("/api/chat/threads");
  return res.threads;
}

export async function getThreadHistory(threadId: string): Promise<ChatMessage[]> {
  const res = await fetchJson<{ thread_id: string; messages: ChatMessage[] }>(
    `/api/chat/history/${threadId}`
  );
  return res.messages;
}

export async function deleteThread(threadId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/history/${threadId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}
