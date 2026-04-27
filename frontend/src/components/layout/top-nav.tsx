"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StockSearch } from "@/components/search/stock-search";
import { syncAll } from "@/services/api";
import { getStoredAuth, isAdmin, login, logout, type AuthUser } from "@/services/auth";
import { showToast } from "@/components/ui/toast";

export function TopNav() {
  const [syncing, setSyncing] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    setUser(getStoredAuth());
  }, []);

  const handleSyncAll = async () => {
    setSyncing(true);
    try {
      const result = await syncAll();
      const { stocks_synced, total_synced, errors } = result;
      const summary = Object.entries(total_synced)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k} ${v}건`)
        .join(", ");
      showToast(
        `전체 동기화 완료 (${stocks_synced.length}개 종목) ${summary || "변경 없음"}`,
        errors.length > 0 ? "info" : "success"
      );
      if (errors.length > 0) {
        showToast(`경고: ${errors[0]}`, "error");
      }
    } catch {
      showToast("전체 동기화 실패. 관리자 로그인이 필요합니다.", "error");
    } finally {
      setSyncing(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const u = await login(email, password);
      setUser(u);
      setShowLogin(false);
      setEmail("");
      setPassword("");
      showToast(`${u.email} 로그인 완료`, "success");
    } catch {
      showToast("로그인 실패", "error");
    }
  };

  const handleLogout = () => {
    logout();
    setUser(null);
    showToast("로그아웃 완료", "info");
  };

  return (
    <nav className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-6 py-3">
      <div className="flex items-center gap-4">
        <Link href="/" className="text-lg font-bold text-slate-50">
          StockInsight
        </Link>
        <StockSearch />
      </div>
      <div className="flex items-center gap-3">
        {isAdmin() && (
          <button
            onClick={handleSyncAll}
            disabled={syncing}
            className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1 text-sm text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
          >
            {syncing ? "동기화 중..." : "전체 동기화"}
          </button>
        )}
        <Link
          href="/chat"
          className="text-sm text-purple-400 transition-colors hover:text-purple-300"
        >
          Ask AI
        </Link>
        <Link
          href="/"
          className="text-sm text-yellow-400 hover:text-yellow-300 transition-colors"
        >
          즐겨찾기
        </Link>
        {user ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">{user.email}</span>
            <button
              onClick={handleLogout}
              className="text-xs text-slate-500 hover:text-slate-300"
            >
              로그아웃
            </button>
          </div>
        ) : (
          <>
            <button
              onClick={() => setShowLogin(!showLogin)}
              className="text-sm text-slate-400 hover:text-slate-200"
            >
              로그인
            </button>
            {showLogin && (
              <form onSubmit={handleLogin} className="absolute right-4 top-14 z-50 rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl">
                <input
                  type="email"
                  placeholder="이메일"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mb-2 w-56 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500"
                />
                <input
                  type="password"
                  placeholder="비밀번호"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mb-3 w-56 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500"
                />
                <button
                  type="submit"
                  className="w-full rounded bg-blue-600 py-1.5 text-sm text-white hover:bg-blue-500"
                >
                  로그인
                </button>
              </form>
            )}
          </>
        )}
      </div>
    </nav>
  );
}
