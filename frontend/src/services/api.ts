import type { Stock, PriceRecord, Analysis } from "@/types/stock";
import type { StockCard } from "@/types/card";
import { getToken } from "@/services/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

async function postJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function searchStocks(query: string): Promise<Stock[]> {
  return fetchJson(`/api/stocks/search?q=${encodeURIComponent(query)}`);
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

export async function removeFavorite(ticker: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/favorites/${ticker}`, {
    method: "DELETE",
    headers: authHeaders(),
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
