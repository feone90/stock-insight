import type { Stock, PriceRecord, Analysis } from "@/types/stock";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
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
  await fetch(`${API_BASE}/api/favorites/${ticker}`, { method: "POST" });
}

export async function removeFavorite(ticker: string): Promise<void> {
  await fetch(`${API_BASE}/api/favorites/${ticker}`, { method: "DELETE" });
}
