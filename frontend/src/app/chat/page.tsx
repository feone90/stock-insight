"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getThreadHistory, streamChat } from "@/services/api";
import { showToast } from "@/components/ui/toast";
import { ChatSidebar } from "@/components/chat/chat-sidebar";
import { MessageList, type ToolCallInProgress } from "@/components/chat/message-list";
import { ChatInput } from "@/components/chat/chat-input";
import type { ChatMessage } from "@/types/chat";

const THREAD_KEY = "stockinsight-chat-thread";
const HINTS = [
  "질문을 이해하고 있어요...",
  "데이터를 조회중이에요...",
  "답변을 준비하고 있어요...",
];
const EXAMPLES = [
  "삼성전자 지금 어때?",
  "반도체 종목 뭐 있어?",
  "테슬라 최근 뉴스 알려줘",
  "SK하이닉스 PER 얼마야?",
];

export default function ChatPage() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingHint, setStreamingHint] = useState(HINTS[0]);
  const [toolCalls, setToolCalls] = useState<ToolCallInProgress[]>([]);
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem(THREAD_KEY);
    if (saved) setThreadId(saved);
  }, []);

  useEffect(() => {
    if (!threadId) {
      setMessages([]);
      localStorage.removeItem(THREAD_KEY);
      return;
    }
    localStorage.setItem(THREAD_KEY, threadId);
    getThreadHistory(threadId)
      .then(setMessages)
      .catch(() => showToast("대화 로드 실패", "error"));
  }, [threadId]);

  useEffect(() => {
    if (!streaming) return;
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % HINTS.length;
      setStreamingHint(HINTS[i]);
    }, 3000);
    return () => clearInterval(interval);
  }, [streaming]);

  const handleSend = useCallback(
    async (message: string) => {
      const userMsg: ChatMessage = {
        role: "user",
        content: message,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);
      setStreamingContent("");
      setStreamingHint(HINTS[0]);
      setToolCalls([]);

      const abort = new AbortController();
      abortRef.current = abort;

      let accumulated = "";
      const roundToolCalls: ToolCallInProgress[] = [];

      try {
        for await (const event of streamChat(message, threadId, abort.signal)) {
          if (event.event === "token") {
            accumulated += event.data.content;
            setStreamingContent(accumulated);
          } else if (event.event === "tool_call") {
            roundToolCalls.push({
              tool: event.data.tool,
              args: event.data.args as Record<string, unknown>,
              key: Date.now() + roundToolCalls.length,
            });
            setToolCalls([...roundToolCalls]);
          } else if (event.event === "done") {
            if (!threadId) setThreadId(event.data.thread_id);
            break;
          } else if (event.event === "error") {
            showToast(event.data.error, "error");
            break;
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          showToast("응답을 중단했어요", "info");
        } else {
          showToast("전송 실패: " + (err as Error).message, "error");
        }
      } finally {
        if (accumulated) {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: accumulated, created_at: new Date().toISOString() },
          ]);
        }
        setStreamingContent(null);
        setStreaming(false);
        abortRef.current = null;
        setSidebarRefresh((x) => x + 1);
      }
    },
    [threadId]
  );

  const handleStop = () => abortRef.current?.abort();

  const handleSelectThread = (id: string | null) => {
    abortRef.current?.abort();
    setThreadId(id);
    setStreamingContent(null);
    setToolCalls([]);
  };

  const isEmpty = messages.length === 0 && !streaming;

  return (
    <div className="lg:pl-60">
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed top-3 left-3 z-50 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 lg:hidden"
        aria-label="대화 목록 열기"
      >
        &#9776;
      </button>

      <ChatSidebar
        activeThreadId={threadId}
        onSelect={handleSelectThread}
        refreshKey={sidebarRefresh}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      {isEmpty ? (
        <div className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-2xl flex-col items-center justify-center px-6 pb-40 text-center">
          <h1 className="mb-3 text-2xl font-bold text-slate-50">안녕하세요</h1>
          <p className="mb-8 text-sm text-slate-400">
            관심 있는 종목에 대해 자연어로 물어보세요.
          </p>
          <div className="grid w-full gap-2 sm:grid-cols-2">
            {EXAMPLES.map((q) => (
              <button
                key={q}
                onClick={() => handleSend(q)}
                className="rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 text-left text-sm text-slate-300 transition-colors hover:border-purple-500/30 hover:bg-purple-500/5"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <MessageList
          messages={messages}
          toolCalls={toolCalls}
          streamingContent={streamingContent}
          streamingHint={streamingHint}
        />
      )}

      <ChatInput streaming={streaming} onSend={handleSend} onStop={handleStop} />
    </div>
  );
}
