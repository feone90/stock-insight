"""Chat agent streaming orchestrator.

LLM adapter의 tool-calling 루프를 돌리며 SSE 이벤트를 yield.
메시지는 generator 완료 시 DB에 persist.
"""

import json
import logging
from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import select

from app.database import async_session
from app.models import ChatMessage
from app.services.chat.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from app.services.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 StockInsight 대화형 주식 어드바이저입니다.
사용자가 종목에 대해 물으면, 반드시 DB tool을 사용해 근거 있는 답변을 하세요.

## Tool 사용 규칙
- 종목명만 말했으면 search_stocks로 ticker를 먼저 확보
- ticker를 알면 get_stock_snapshot으로 기본 정보 조회
- 사용자가 '뉴스', '소식'을 물으면 get_recent_news 사용
- tool이 {"error": ...}를 반환하면 자연어로 안내

## 답변 포맷 규칙
- **한국어**로 답변
- 짧은 요약 한 줄로 시작 (예: "삼성전자는 현재 긍정적 흐름입니다.")
- 핵심 데이터를 **표** 또는 **목록**으로 정리:
  - 현재가, 등락률 등 숫자는 볼드 처리
  - 뉴스는 제목 + 날짜를 리스트로
  - 재무지표는 간단한 표로
- 마지막에 한 줄 의견 또는 참고사항 추가
- 전체 3~5문단 이내로 간결하게
- 투자 권유 면책 문구를 길게 달지 않기
"""

MAX_CONTEXT_TURNS = 20
MAX_TOOL_ROUNDS = 5


async def _load_history(thread_id: UUID, user_id: str) -> list[dict]:
    """thread_id의 최근 N턴을 LLM messages 포맷으로 로드."""
    async with async_session() as db:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id, ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(MAX_CONTEXT_TURNS)
        )
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [{"role": r.role, "content": r.content} for r in rows]


async def _persist_messages(thread_id: UUID, user_id: str, messages: list[dict]) -> None:
    """새 메시지들을 DB에 저장."""
    async with async_session() as db:
        for m in messages:
            db.add(ChatMessage(
                thread_id=thread_id,
                user_id=user_id,
                role=m["role"],
                content=m.get("content", ""),
                tool_calls=m.get("tool_calls"),
            ))
        await db.commit()


async def stream_chat(
    adapter: LLMAdapter,
    thread_id: UUID,
    user_id: str,
    user_message: str,
) -> AsyncGenerator[dict, None]:
    """SSE 이벤트 async generator.

    Yields:
      {"event": "token", "data": {"content": "..."}}
      {"event": "tool_call", "data": {"tool": "...", "args": {...}}}
      {"event": "done", "data": {"thread_id": "...", "message_count": N}}
      {"event": "error", "data": {"error": "..."}}
    """
    new_messages: list[dict] = [{"role": "user", "content": user_message}]

    try:
        history = await _load_history(thread_id, user_id)
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}] + history + new_messages

        assistant_content = ""
        tool_calls_log: list[dict] = []

        for _round in range(MAX_TOOL_ROUNDS):
            tool_invocations = []
            async for event in adapter.chat_with_tools(conversation, TOOL_SCHEMAS):
                if event["type"] == "text":
                    chunk = event["content"]
                    assistant_content += chunk
                    yield {"event": "token", "data": {"content": chunk}}
                elif event["type"] == "function_call":
                    tool_invocations.append(event)
                    yield {
                        "event": "tool_call",
                        "data": {"tool": event["name"], "args": event["arguments"]},
                    }
                elif event["type"] == "done":
                    break

            if not tool_invocations:
                break

            # Execute tools and feed results back
            for inv in tool_invocations:
                func = TOOL_FUNCTIONS.get(inv["name"])
                if not func:
                    tool_result = {"error": f"알 수 없는 tool: {inv['name']}"}
                else:
                    try:
                        tool_result = await func(**inv["arguments"])
                    except Exception as e:
                        logger.warning("Tool %s failed: %s", inv["name"], e)
                        tool_result = {"error": str(e)}

                tool_calls_log.append({
                    "name": inv["name"],
                    "arguments": inv["arguments"],
                    "result": tool_result,
                })

                # Append tool call + result to conversation for next round
                conversation.append({
                    "type": "function_call",
                    "call_id": inv.get("call_id", ""),
                    "name": inv["name"],
                    "arguments": json.dumps(inv["arguments"], ensure_ascii=False),
                })
                conversation.append({
                    "type": "function_call_output",
                    "call_id": inv.get("call_id", ""),
                    "output": json.dumps(tool_result, ensure_ascii=False),
                })

        new_messages.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": {"invocations": tool_calls_log} if tool_calls_log else None,
        })

        yield {
            "event": "done",
            "data": {"thread_id": str(thread_id), "message_count": len(new_messages)},
        }

    except Exception as e:
        logger.exception("stream_chat failed")
        yield {"event": "error", "data": {"error": str(e)}}
    finally:
        if assistant_content and len(new_messages) == 1:
            new_messages.append({"role": "assistant", "content": assistant_content})
        try:
            await _persist_messages(thread_id, user_id, new_messages)
        except Exception as e:
            logger.error("Failed to persist messages: %s", e)
