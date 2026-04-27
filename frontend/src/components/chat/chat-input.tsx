"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  streaming: boolean;
  onSend: (message: string) => void;
  onStop: () => void;
  autoFocus?: boolean;
}

export function ChatInput({ streaming, onSend, onStop, autoFocus = true }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [value]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    } else if (e.key === "Escape") {
      e.currentTarget.blur();
    }
  };

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || streaming) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-slate-800 bg-slate-950/95 backdrop-blur-sm pb-[env(safe-area-inset-bottom)] lg:left-60">
      <div className="mx-auto flex max-w-3xl items-end gap-2 px-4 py-3">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder="질문을 입력하세요 (Enter: 전송, Shift+Enter: 줄바꿈)"
          disabled={streaming}
          rows={1}
          className="flex-1 resize-none rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-50 placeholder:text-slate-600 focus:border-purple-500/50 focus:outline-none focus:ring-1 focus:ring-purple-500/50 disabled:opacity-50"
        />
        {streaming ? (
          <button
            onClick={onStop}
            aria-label="응답 중단"
            className="flex h-11 w-11 min-h-[44px] min-w-[44px] items-center justify-center rounded-xl border border-red-500/30 bg-red-500/10 text-red-400 transition-colors hover:bg-red-500/20"
          >
            &#9632;
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!value.trim()}
            aria-label="전송"
            className="flex h-11 w-11 min-h-[44px] min-w-[44px] items-center justify-center rounded-xl border border-purple-500/30 bg-purple-500/10 text-purple-400 transition-colors hover:bg-purple-500/20 disabled:opacity-30"
          >
            &#10148;
          </button>
        )}
      </div>
    </div>
  );
}
