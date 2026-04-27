"""Probe chat agent for capability gaps — manual review of answers.

Unlike eval_chat_tools.py (pass/fail on tool selection), this script throws
questions the agent likely *can't* answer well, captures the response, and
writes a markdown report. Decide which gaps to close based on the output.

Run:  cd backend && uv run python -m scripts.probe_chat_gaps
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete

from app.database import async_session
from app.models import ChatMessage
from app.services.chat.stream import stream_chat
from app.services.llm.adapter import get_adapter

PROBE_USER_ID = "probe-bot@stockinsight.local"

# (label, question) — see CLAUDE.md / docs/ARCHITECTURE.md for which DB tables
# are reachable through current tools.
PROBES: list[tuple[str, str]] = [
    ("1. 시계열 가격 (사용자 발견)",
     "MSFT 최근 한 달 중 가장 많이 떨어진 날 알려줘"),
    ("2. 변동성 / 추세",
     "삼성전자 지난 30일 가격 변동성 어땠어?"),
    ("3. 공시 (Disclosure)",
     "삼성전자 최근 공시 알려줘"),
    ("4. 환율",
     "원/달러 환율 알려줘"),
    ("5. 즐겨찾기 / 개인 컨텍스트",
     "내 즐겨찾기 종목 중 최근에 가장 많이 오른 거 알려줘"),
    ("6. 재무 시계열",
     "삼성전자 PER 1년 추이 알려줘"),
    ("7. 뉴스 본문 활용",
     "TSLA 최근 뉴스 본문 핵심만 요약해줘"),
    ("8. 섹터 / 시장 필터",
     "반도체 섹터 종목 뭐있어?"),
    ("9. 시계열 + 이벤트 결합",
     "지난주 MSFT 가장 많이 떨어진 날 무슨 뉴스 있었어?"),
]


async def cleanup() -> int:
    async with async_session() as db:
        r = await db.execute(
            delete(ChatMessage).where(ChatMessage.user_id == PROBE_USER_ID)
        )
        await db.commit()
        return r.rowcount or 0


async def run_one(question: str) -> tuple[list[str], str, str]:
    adapter = get_adapter()
    thread_id = uuid4()
    tools_called: list[str] = []
    answer_parts: list[str] = []
    err = ""
    try:
        async for ev in stream_chat(
            adapter=adapter,
            thread_id=thread_id,
            user_id=PROBE_USER_ID,
            user_message=question,
        ):
            t = ev["event"]
            d = ev["data"]
            if t == "token":
                answer_parts.append(d.get("content", ""))
            elif t == "tool_call":
                tools_called.append(d.get("tool", ""))
            elif t == "error":
                err = d.get("error", "")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    return tools_called, "".join(answer_parts), err


async def main() -> int:
    deleted = await cleanup()
    print(f"Cleaned {deleted} prior probe rows.")
    results = []
    for i, (label, q) in enumerate(PROBES, 1):
        print(f"[{i}/{len(PROBES)}] {label}")
        print(f"      Q: {q}")
        tools, ans, err = await run_one(q)
        print(f"      tools={tools}  err={err or '-'}")
        results.append((label, q, tools, ans, err))

    lines = [
        "# Phase A — Chat agent gap probe",
        "",
        f"- Run at: {datetime.now(timezone.utc).isoformat()}",
        f"- Probes: {len(PROBES)}",
        "",
    ]
    for label, q, tools, ans, err in results:
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"**Q:** {q}")
        lines.append("")
        lines.append(f"**Tools called:** `{tools}`")
        if err:
            lines.append("")
            lines.append(f"**Error:** `{err}`")
        snip = (ans or "").strip()
        if len(snip) > 800:
            snip = snip[:800] + " ..."
        lines.append("")
        lines.append("**Answer:**")
        lines.append("")
        lines.append("```")
        lines.append(snip or "(empty)")
        lines.append("```")
        lines.append("")

    out_dir = Path(__file__).resolve().parents[2] / "docs" / "gstack"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"phase-a-gap-probe-{ts}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {out_path}")

    await cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
