"use client";

/**
 * 가족 dev 전용 user picker — localStorage 기반.
 * 인증 X. 단순히 X-User-Id header label로 즐겨찾기를 분리하는 용도.
 */

const USERS_KEY = "stockinsight.users";
const ACTIVE_KEY = "stockinsight.activeUser";
const EVENT_NAME = "stockinsight.userchanged";

export function getUsers(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(USERS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function getActiveUser(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACTIVE_KEY);
}

export function addUser(name: string): string[] {
  const trimmed = name.trim().slice(0, 64);
  if (!trimmed) return getUsers();
  const list = getUsers();
  if (list.includes(trimmed)) {
    setActiveUser(trimmed);
    return list;
  }
  const next = [...list, trimmed];
  localStorage.setItem(USERS_KEY, JSON.stringify(next));
  if (!getActiveUser()) {
    localStorage.setItem(ACTIVE_KEY, trimmed);
  }
  window.dispatchEvent(new Event(EVENT_NAME));
  return next;
}

export function setActiveUser(name: string): void {
  localStorage.setItem(ACTIVE_KEY, name);
  window.dispatchEvent(new Event(EVENT_NAME));
}

export function removeUser(name: string): string[] {
  const list = getUsers().filter((u) => u !== name);
  localStorage.setItem(USERS_KEY, JSON.stringify(list));
  if (getActiveUser() === name) {
    localStorage.setItem(ACTIVE_KEY, list[0] || "");
  }
  window.dispatchEvent(new Event(EVENT_NAME));
  return list;
}

export function onUserChanged(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(EVENT_NAME, callback);
  return () => window.removeEventListener(EVENT_NAME, callback);
}
