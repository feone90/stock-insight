const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "stockinsight_token";
const USER_KEY = "stockinsight_user";

export interface AuthUser {
  email: string;
  role: string;
  token: string;
}

export function getStoredAuth(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem(TOKEN_KEY);
  const user = localStorage.getItem(USER_KEY);
  if (!token || !user) return null;
  try {
    return { ...JSON.parse(user), token };
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function isAdmin(): boolean {
  if (process.env.NODE_ENV === "development") return true;
  const auth = getStoredAuth();
  return auth?.role === "admin";
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error("로그인 실패");
  }
  const data = await res.json();
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify({ email: data.email, role: data.role }));
  return { email: data.email, role: data.role, token: data.access_token };
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}
