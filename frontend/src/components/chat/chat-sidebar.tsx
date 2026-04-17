"use client";

import { useEffect, useRef, useState } from "react";
import { deleteThread, listThreads } from "@/services/api";
import { showToast } from "@/components/ui/toast";
import type { ThreadSummary } from "@/types/chat";

interface Props {
  activeThreadId: string | null;
  onSelect: (threadId: string | null) => void;
  refreshKey: number;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function ChatSidebar({ activeThreadId, onSelect, refreshKey, mobileOpen, onMobileClose }: Props) {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const timerRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    setLoading(true);
    listThreads()
      .then(setThreads)
      .catch(() => showToast("대화 목록 로드 실패", "error"))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const handleDelete = (threadId: string) => {
    setHidden((prev) => new Set(prev).add(threadId));
    showToast("대화를 삭제했어요", "info");

    timerRef.current[threadId] = setTimeout(() => {
      deleteThread(threadId)
        .then(() => {
          setThreads((prev) => prev.filter((t) => t.thread_id !== threadId));
          if (activeThreadId === threadId) onSelect(null);
        })
        .catch(() => {
          showToast("삭제 실패", "error");
          setHidden((prev) => { const n = new Set(prev); n.delete(threadId); return n; });
        });
      delete timerRef.current[threadId];
    }, 5000);
  };

  const visibleThreads = threads.filter((t) => !hidden.has(t.thread_id));

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={onMobileClose} aria-hidden />
      )}
      <aside
        className={`fixed top-14 bottom-0 left-0 z-40 w-60 border-r border-slate-800 bg-slate-950 transition-transform lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col">
          <div className="border-b border-slate-800 p-3">
            <button
              onClick={() => { onSelect(null); onMobileClose(); }}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-slate-800"
            >
              + 새 대화
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {loading && <div className="p-2 text-xs text-slate-600">로딩 중...</div>}
            {!loading && visibleThreads.length === 0 && (
              <div className="p-2 text-xs text-slate-600">아직 대화 없음</div>
            )}
            {visibleThreads.map((t) => (
              <div
                key={t.thread_id}
                className={`group mb-1 flex items-center gap-1 rounded-md px-2 py-2 text-xs transition-colors ${
                  activeThreadId === t.thread_id
                    ? "border border-purple-500/30 bg-purple-500/5"
                    : "hover:bg-slate-900"
                }`}
              >
                <button
                  onClick={() => { onSelect(t.thread_id); onMobileClose(); }}
                  className="flex-1 truncate text-left text-slate-300"
                  title={t.preview}
                >
                  {t.preview || "(빈 대화)"}
                </button>
                <button
                  onClick={() => handleDelete(t.thread_id)}
                  aria-label="삭제"
                  className="opacity-0 text-slate-600 transition-opacity hover:text-red-400 group-hover:opacity-100"
                >
                  x
                </button>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
  );
}
