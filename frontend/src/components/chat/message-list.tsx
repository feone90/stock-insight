"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./message-bubble";
import { ToolCallBadge } from "./tool-call-badge";
import type { ChatMessage } from "@/types/chat";

export interface ToolCallInProgress {
  tool: string;
  args: Record<string, unknown>;
  key: number;
}

interface Props {
  messages: ChatMessage[];
  toolCalls: ToolCallInProgress[];
  streamingContent: string | null;
  streamingHint: string;
}

export function MessageList({ messages, toolCalls, streamingContent, streamingHint }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingContent, toolCalls]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-40 pt-4" role="log" aria-live="polite">
      {messages.map((m, i) => (
        <MessageBubble key={i} message={m} />
      ))}
      {toolCalls.map((tc) => (
        <ToolCallBadge key={tc.key} tool={tc.tool} args={tc.args} completed />
      ))}
      {streamingContent !== null && (
        <MessageBubble
          message={{
            role: "assistant",
            content: streamingContent || streamingHint,
            created_at: new Date().toISOString(),
          }}
          streaming
        />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
