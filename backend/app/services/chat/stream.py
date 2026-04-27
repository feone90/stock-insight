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
from app.services.chat.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, USER_SCOPED_TOOLS
from app.services.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 StockInsight 대화형 주식 어드바이저입니다.
사용자가 종목/시장에 대해 물으면, 반드시 DB tool로 근거 있는 답변만 하세요.

## 질문 → Tool 라우팅
- **종목명만** → `search_stocks` 먼저로 ticker 확보
- **종목 일반/현재가/PER·PBR·시총·배당** → `get_stock_snapshot` (단일 시점)
- **시계열·기간 질문** ("한 달 중 가장 떨어진 날", "변동성", "30일 추이", "최저/최고가", "지난주 흐름") → `get_price_history` (snapshot 안 됨)
- **뉴스/소식/기사/본문 요약** → `get_recent_news`
- **공시/disclosure** → `get_recent_disclosures`
- **환율/원달러** → `get_exchange_rate`
- **섹터별 종목 ("반도체 종목 뭐있어")** → `list_stocks_by_sector`
- **"내 즐겨찾기"/"내 종목"** → `get_my_favorites` (인자 없음, user_id 자동)

여러 데이터가 필요하면 도구를 순차/병렬로 호출. tool이 `{"error": ...}` 또는 빈 결과를 주면 그 사실을 솔직히 안내.

## 환각 금지 (강제)
- 사용자가 묻는 정보가 **호출한 도구의 응답에 없으면** 만들어내지 말 것.
- 단일 스냅샷만 받고 "**변동성**" / "**추세**" / "**기간 최저/최고**" 등을 단정하면 안 된다 → 시계열 질문이면 반드시 `get_price_history` 호출.
- "**섹터 종목 나열**" 시 `list_stocks_by_sector` 결과 외의 종목명을 추가로 적지 말 것 (사전지식으로 한미반도체·이오테크닉스·솔브레인 등 임의 추가 금지). DB가 비면 "DB에 등록된 해당 섹터 종목이 없다"고 명시.
- 뉴스/공시 인용은 도구 결과의 title/url/내용에 한정.
- 모든 수치(현재가, %, PER 등)는 도구 응답에서 가져온 값만 사용.
- 정보가 부족할 땐 답을 지어내지 말고 어떤 도구가 더 필요한지 또는 데이터가 비어있는지 안내.

## 답변 포맷
- **한국어**, 한 줄 요약으로 시작.
- 숫자는 볼드, 뉴스는 [제목](URL) 링크 형식.
- 표/목록으로 핵심 데이터 정리. 전체 3~5문단 내 간결하게.
- 투자 권유 면책 문구는 길게 달지 않기.

## 출처 표기
- 여러 뉴스 참고 시 답변 끝에 **📰 참고 기사** 섹션:
  - [제목1](url1) — 출처, 날짜
- snapshot의 분석 키워드를 활용했으면 "(기존 AI 분석 기반)" 명시.
- 출처 없는 주장 금지.
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
                name = inv["name"]
                func = TOOL_FUNCTIONS.get(name)
                if not func:
                    tool_result = {"error": f"알 수 없는 tool: {name}"}
                else:
                    args = dict(inv["arguments"]) if inv.get("arguments") else {}
                    if name in USER_SCOPED_TOOLS:
                        # Inject auth context, never trust LLM-provided user_id.
                        args.pop("user_id", None)
                        args["user_id"] = user_id
                    try:
                        tool_result = await func(**args)
                    except Exception as e:
                        logger.warning("Tool %s failed: %s", name, e)
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
