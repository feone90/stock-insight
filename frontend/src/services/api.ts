import type { Stock, PriceRecord, Analysis } from "@/types/stock";
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

export async function syncStock(ticker: string): Promise<SyncResult> {
  return postJson(`/api/admin/sync/stock/${ticker}`);
}

export async function syncAll(): Promise<SyncAllResult> {
  return postJson(`/api/admin/sync/all`);
}
