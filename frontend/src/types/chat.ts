export type ChatRole = "user" | "assistant" | "tool";

export interface ChatMessage {
  role: ChatRole;
  content: string;
  tool_calls?: {
    invocations: Array<{
      name: string;
      arguments: Record<string, unknown>;
      result: unknown;
    }>;
  } | null;
  created_at: string;
}

export interface ThreadSummary {
  thread_id: string;
  preview: string;
  last_updated: string;
}

export type SseEvent =
  | { event: "token"; data: { content: string } }
  | { event: "tool_call"; data: { tool: string; args: Record<string, unknown> } }
  | { event: "done"; data: { thread_id: string; message_count: number } }
  | { event: "error"; data: { error: string } };
