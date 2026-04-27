"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "@/types/chat";

interface Props {
  message: ChatMessage;
  streaming?: boolean;
}

// CommonMark emphasis flanking fails when `**` sits between a punctuation
// character and a CJK / letter character (e.g. `**-3.97%**입니다`). Insert a
// space on the failing boundary so the parser sees a valid right/left flank.
function fixEmphasisBoundaries(s: string): string {
  return s
    // Opening `**`: letter/digit immediately before, punctuation immediately after.
    .replace(/([\p{L}\p{N}])(\*\*)(?=\p{P})/gu, "$1 $2")
    // Closing `**`: punctuation immediately before, letter/digit immediately after.
    .replace(/(\p{P})(\*\*)(?=[\p{L}\p{N}])/gu, "$1$2 ");
}

export function MessageBubble({ message, streaming = false }: Props) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const timestamp = new Date(message.created_at).toLocaleString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className={`group flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`relative ${
          isUser
            ? "max-w-[75%] sm:max-w-[60%] rounded-2xl rounded-tr-sm border border-slate-700 bg-slate-800 px-4 py-2.5 text-slate-50"
            : "max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-tl-sm border border-purple-500/20 bg-purple-500/5 px-4 py-2.5 text-slate-200"
        }`}
      >
        {!isUser && (
          <div className="mb-1 text-xs font-medium text-purple-400">
            StockInsight AI
          </div>
        )}

        {isUser ? (
          <div className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </div>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none text-sm leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content
                ? fixEmphasisBoundaries(message.content)
                : streaming
                  ? "질문을 이해하고 있어요..."
                  : ""}
            </ReactMarkdown>
            {streaming && <span className="inline-block ml-0.5 w-2 h-4 bg-slate-400 animate-pulse" />}
          </div>
        )}

        <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-slate-600 opacity-0 transition-opacity group-hover:opacity-100">
          <span>{timestamp}</span>
          {!isUser && message.content && (
            <button
              onClick={handleCopy}
              className="rounded px-1 hover:bg-slate-700/50 hover:text-slate-300"
              aria-label="복사"
            >
              {copied ? "복사됨" : "복사"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
