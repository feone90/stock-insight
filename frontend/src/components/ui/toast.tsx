"use client";

import { useEffect, useState } from "react";

interface Toast {
  id: number;
  message: string;
  type: "success" | "error" | "info";
}

let toastId = 0;
let addToastFn: ((toast: Toast) => void) | null = null;

export function showToast(message: string, type: "success" | "error" | "info" = "info") {
  addToastFn?.({ id: ++toastId, message, type });
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    addToastFn = (toast) => setToasts((prev) => [...prev, toast]);
    return () => { addToastFn = null; };
  }, []);

  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setTimeout(() => {
      setToasts((prev) => prev.slice(1));
    }, 4000);
    return () => clearTimeout(timer);
  }, [toasts]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`rounded-lg px-4 py-3 text-sm shadow-lg backdrop-blur-sm transition-all max-w-sm ${
            t.type === "success"
              ? "border border-green-800 bg-green-950/90 text-green-200"
              : t.type === "error"
              ? "border border-red-800 bg-red-950/90 text-red-200"
              : "border border-slate-700 bg-slate-900/90 text-slate-200"
          }`}
        >
          <span className="mr-2">
            {t.type === "success" ? "✓" : t.type === "error" ? "✕" : "ℹ"}
          </span>
          {t.message}
        </div>
      ))}
    </div>
  );
}
