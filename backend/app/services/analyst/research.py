"""Stage 1: Research agent. Cheap-tier LLM with broad tool access.

Loops the chat_with_tools async generator until the LLM stops calling tools or
max_rounds is reached. Aggregates tool results into the message thread, parses
the final JSON-shaped findings response, and returns a dict the synthesizer
(Stage 2) can consume.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.analyst import get_analyst_adapter
from app.services.analyst.persona import RESEARCHER_V1, RESEARCHER_VERSION
from app.services.analyst.tools import (
    RESEARCH_TOOL_SCHEMAS,
    dispatch_research_tool,
)

logger = logging.getLogger(__name__)


async def _consume_one_round(adapter, messages: list[dict], tools: list[dict]) -> tuple[list[dict], str]:
    """Run one chat_with_tools round; return (tool_calls, accumulated_text)."""
    tool_calls: list[dict] = []
    text_parts: list[str] = []
    async for evt in adapter.chat_with_tools(messages=messages, tools=tools):
        et = evt.get("type")
        if et == "text":
            text_parts.append(evt.get("content", ""))
        elif et == "function_call":
            tool_calls.append(
                {
                    "name": evt.get("name", ""),
                    "arguments": evt.get("arguments", {}),
                    "call_id": evt.get("call_id", ""),
                }
            )
        # "done" → end of stream
    return tool_calls, "".join(text_parts)


async def run_research(ticker: str, max_rounds: int = 10) -> dict:
    """Loop the research LLM with tools. Returns aggregated findings JSON.

    Output shape:
    {
      "findings": [...],
      "citations": [...],
      "gaps_noted": [...],
      "rounds_used": int,
      "max_rounds_hit": bool,  # only when cap was hit
      "researcher_version": "researcher_v1"
    }
    """
    user_prompt = (
        f"종목 ticker = {ticker}. 위 원칙대로 조사를 시작하라. "
        "마지막엔 반드시 JSON 객체 (findings/citations/gaps_noted) 로 응답."
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": RESEARCHER_V1},
        {"role": "user", "content": user_prompt},
    ]

    adapter = get_analyst_adapter()
    rounds_used = 0

    for _ in range(max_rounds):
        rounds_used += 1
        tool_calls, content = await _consume_one_round(
            adapter, messages, RESEARCH_TOOL_SCHEMAS
        )

        if not tool_calls:
            # LLM produced final answer
            try:
                parsed = json.loads(content) if content else {"findings": []}
            except json.JSONDecodeError:
                parsed = {
                    "findings": [],
                    "raw_content": content,
                    "parse_error": "non-json final response",
                }
            parsed["rounds_used"] = rounds_used
            parsed["researcher_version"] = RESEARCHER_VERSION
            return parsed

        # Append each tool call + its result as Foundry Responses API top-level
        # items (NOT OpenAI chat-completions assistant/tool messages).
        for call in tool_calls:
            tool_result = await dispatch_research_tool(
                call["name"], call.get("arguments", {})
            )
            messages.append(
                {
                    "type": "function_call",
                    "call_id": call.get("call_id", ""),
                    "name": call["name"],
                    "arguments": json.dumps(
                        call.get("arguments", {}), ensure_ascii=False
                    ),
                }
            )
            messages.append(
                {
                    "type": "function_call_output",
                    "call_id": call.get("call_id", ""),
                    "output": json.dumps(tool_result, ensure_ascii=False, default=str)[:8000],
                }
            )

    # max_rounds hit — flush a final answer with empty tool list
    messages.append(
        {
            "role": "user",
            "content": "max rounds 도달. 지금까지 모은 증거로 findings JSON을 즉시 반환하라.",
        }
    )
    _, content = await _consume_one_round(adapter, messages, [])
    try:
        parsed = json.loads(content) if content else {"findings": []}
    except json.JSONDecodeError:
        parsed = {"findings": [], "raw_content": content}
    parsed["rounds_used"] = rounds_used
    parsed["max_rounds_hit"] = True
    parsed["researcher_version"] = RESEARCHER_VERSION
    return parsed
