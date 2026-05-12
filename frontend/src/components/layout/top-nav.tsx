"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StockSearch } from "@/components/search/stock-search";
import { syncAll } from "@/services/api";
import { getStoredAuth, isAdmin, login, logout, type AuthUser } from "@/services/auth";
import {
  addUser,
  getActiveUser,
  getUsers,
  onUserChanged,
  removeUser,
  setActiveUser,
} from "@/services/user";
import { showToast } from "@/components/ui/toast";

export function TopNav() {
  const [syncing, setSyncing] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // 가족 user picker (localStorage 기반)
  const [users, setUsers] = useState<string[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [newUserName, setNewUserName] = useState("");

  useEffect(() => {
    setUser(getStoredAuth());
    setUsers(getUsers());
    setActive(getActiveUser());
    return onUserChanged(() => {
      setUsers(getUsers());
      setActive(getActiveUser());
    });
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

  const handleAddUser = (e: React.FormEvent) => {
    e.preventDefault();
    const name = newUserName.trim();
    if (!name) return;
    addUser(name);
    setActiveUser(name);
    setNewUserName("");
    setShowPicker(false);
    showToast(`사용자 '${name}'으로 전환됨`, "success");
  };

  const handleSwitchUser = (name: string) => {
    setActiveUser(name);
    setShowPicker(false);
    showToast(`'${name}'으로 전환됨`, "success");
  };

  const handleRemoveUser = (name: string, ev: React.MouseEvent) => {
    ev.stopPropagation();
    if (!confirm(`'${name}' 사용자를 삭제하시겠어요? 즐겨찾기 데이터는 서버에 남습니다.`)) return;
    removeUser(name);
  };

  return (
    <nav className="flex flex-wrap items-center justify-between gap-y-2 border-b border-slate-800 bg-slate-950 px-3 py-2 md:px-6 md:py-3">
      <div className="flex items-center gap-2 md:gap-4">
        <Link href="/" className="text-base md:text-lg font-bold text-slate-50">
          StockInsight
        </Link>
        <StockSearch />
      </div>
      <div className="flex items-center gap-2 md:gap-3">
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

        {/* 가족 user picker — 인증 없이 즐겨찾기 분리 */}
        <div className="relative">
          <button
            onClick={() => setShowPicker((v) => !v)}
            className="flex items-center gap-1 rounded-md border border-slate-700 bg-slate-800 px-3 py-1 text-sm text-slate-200 hover:bg-slate-700"
          >
            <span>👤</span>
            <span>{active || "사용자 선택"}</span>
            <span className="text-xs text-slate-500">▼</span>
          </button>
          {showPicker && (
            <div className="absolute right-0 top-9 z-50 w-56 rounded-lg border border-slate-700 bg-slate-900 p-2 shadow-xl">
              {users.length === 0 ? (
                <p className="px-2 py-2 text-xs text-slate-500">
                  사용자 없음 — 아래에 이름 입력해 추가
                </p>
              ) : (
                <ul className="mb-2 max-h-40 overflow-y-auto">
                  {users.map((u) => (
                    <li
                      key={u}
                      onClick={() => handleSwitchUser(u)}
                      className={`group flex cursor-pointer items-center justify-between rounded px-2 py-1.5 text-sm hover:bg-slate-800 ${
                        u === active ? "text-yellow-300" : "text-slate-200"
                      }`}
                    >
                      <span>{u === active ? "✓ " : ""}{u}</span>
                      <button
                        onClick={(ev) => handleRemoveUser(u, ev)}
                        className="invisible text-xs text-slate-500 hover:text-red-400 group-hover:visible"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <form onSubmit={handleAddUser} className="flex gap-1 border-t border-slate-800 pt-2">
                <input
                  type="text"
                  placeholder="새 사용자 이름"
                  value={newUserName}
                  onChange={(e) => setNewUserName(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 outline-none focus:border-blue-500"
                  maxLength={32}
                />
                <button
                  type="submit"
                  className="rounded bg-blue-600 px-2 py-1 text-sm text-white hover:bg-blue-500"
                >
                  +
                </button>
              </form>
            </div>
          )}
        </div>

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
