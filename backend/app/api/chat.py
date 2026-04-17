"""Chat API — SSE streaming + history CRUD."""

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserInfo, get_current_user
from app.database import get_db
from app.models import ChatMessage
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatRequest,
    DeleteResponse,
    ThreadListResponse,
    ThreadSummary,
)
from app.services.chat.stream import stream_chat
from app.services.llm.adapter import get_adapter

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("")
async def post_chat(
    req: ChatRequest,
    user: UserInfo = Depends(get_current_user),
):
    thread_id = req.thread_id or uuid4()
    adapter = get_adapter()

    async def event_source():
        async for event in stream_chat(
            adapter=adapter,
            thread_id=thread_id,
            user_id=user.email,
            user_message=req.message,
        ):
            yield _format_sse(event["event"], event["data"])

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 thread 목록."""
    subq = (
        select(
            ChatMessage.thread_id,
            func.max(ChatMessage.created_at).label("last_updated"),
        )
        .where(ChatMessage.user_id == user.email)
        .group_by(ChatMessage.thread_id)
        .subquery()
    )
    result = await db.execute(
        select(subq).order_by(desc(subq.c.last_updated)).limit(50)
    )
    rows = result.all()

    threads: list[ThreadSummary] = []
    for row in rows:
        tid = row.thread_id
        first_result = await db.execute(
            select(ChatMessage.content)
            .where(
                ChatMessage.thread_id == tid,
                ChatMessage.user_id == user.email,
                ChatMessage.role == "user",
            )
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
        first = first_result.scalar_one_or_none() or ""
        threads.append(ThreadSummary(
            thread_id=tid,
            preview=first[:80],
            last_updated=row.last_updated.isoformat(),
        ))

    return ThreadListResponse(threads=threads)


@router.get("/history/{thread_id}", response_model=ChatHistoryResponse)
async def get_history(
    thread_id: UUID,
    user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """특정 thread 메시지 이력 (소유권 검증 포함)."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id, ChatMessage.user_id == user.email)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = [
        ChatMessageResponse(
            role=r.role,
            content=r.content,
            tool_calls=r.tool_calls,
            created_at=r.created_at.isoformat(),
        )
        for r in result.scalars().all()
    ]
    return ChatHistoryResponse(thread_id=thread_id, messages=messages)


@router.delete("/history/{thread_id}", response_model=DeleteResponse)
async def delete_history(
    thread_id: UUID,
    user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """thread 삭제 (소유권 검증 포함)."""
    stmt = delete(ChatMessage).where(
        ChatMessage.thread_id == thread_id,
        ChatMessage.user_id == user.email,
    )
    result = await db.execute(stmt)
    await db.commit()
    return DeleteResponse(status="deleted", rows=result.rowcount or 0)
