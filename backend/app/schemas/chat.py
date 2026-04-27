from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    thread_id: UUID | None = None


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    tool_calls: dict | None = None
    created_at: str


class ChatHistoryResponse(BaseModel):
    thread_id: UUID
    messages: list[ChatMessageResponse]


class ThreadSummary(BaseModel):
    thread_id: UUID
    preview: str
    last_updated: str


class ThreadListResponse(BaseModel):
    threads: list[ThreadSummary]


class DeleteResponse(BaseModel):
    status: str
    rows: int
