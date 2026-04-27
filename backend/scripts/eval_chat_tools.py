"""Phase A ship gate — Korean tool-selection eval.

Runs 20 representative Korean questions through the chat agent and scores:
  - tool_match: did the agent call the expected tool(s)?
  - evidence_match: does the answer contain at least one expected keyword?

Usage:
  cd backend
  uv run python -m scripts.eval_chat_tools

Outputs a markdown report at docs/gstack/phase-a-eval-<timestamp>.md.
Eval messages are persisted under user_id="eval-bot@stockinsight.local" and
cleaned up at the start of each run so the production tables stay tidy.
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete

from app.database import async_session
from app.models import ChatMessage
from app.services.chat.stream import stream_chat
from app.services.llm.adapter import get_adapter

EVAL_USER_ID = "eval-bot@stockinsight.local"


@dataclass
class EvalCase:
    id: int
    question: str
    category: str
    tools_required: list[str] = field(default_factory=list)
    tools_forbidden: list[str] = field(default_factory=list)
    evidence_any: list[str] = field(default_factory=list)
    note: str = ""


CASES: list[EvalCase] = [
    # 종목 일반 질문 — snapshot 기대
    EvalCase(1, "삼성전자 어때?", "snapshot",
             tools_required=["get_stock_snapshot"],
             evidence_any=["삼성전자", "005930"]),
    EvalCase(2, "TSLA 어때?", "snapshot",
             tools_required=["get_stock_snapshot"],
             evidence_any=["Tesla", "TSLA", "테슬라"]),
    EvalCase(3, "애플 주가 알려줘", "snapshot",
             tools_required=["get_stock_snapshot"],
             evidence_any=["Apple", "AAPL", "애플"],
             note="search_stocks 먼저 호출해도 OK"),
    EvalCase(4, "카카오 PER 얼마야?", "financial",
             tools_required=["get_stock_snapshot"],
             evidence_any=["PER", "주가수익", "Kakao", "카카오"]),
    EvalCase(5, "SK하이닉스 시가총액 알려줘", "financial",
             tools_required=["get_stock_snapshot"],
             evidence_any=["시가총액", "SK", "하이닉스", "000660"]),
    EvalCase(6, "네이버 배당수익률 어때?", "financial",
             tools_required=["get_stock_snapshot"],
             evidence_any=["배당", "NAVER", "네이버"]),
    # 뉴스 명시 — news 기대
    EvalCase(7, "MSFT 최근 뉴스 알려줘", "news",
             tools_required=["get_recent_news"],
             evidence_any=["뉴스", "기사", "Microsoft", "MSFT"]),
    EvalCase(8, "삼성전자 뉴스 보여줘", "news",
             tools_required=["get_recent_news"],
             evidence_any=["뉴스", "기사", "삼성"]),
    EvalCase(9, "테슬라 최근 7일 소식 알려줘", "news",
             tools_required=["get_recent_news"],
             evidence_any=["뉴스", "소식", "기사", "Tesla", "테슬라"]),
    EvalCase(10, "TSLA 최근 무슨 일 있었어?", "news",
             tools_required=["get_recent_news"],
             evidence_any=["뉴스", "기사", "소식"],
             note="'무슨 일'은 뉴스 신호"),
    # 분석/요약
    EvalCase(11, "카카오 분석 요약해줘", "snapshot",
             tools_required=["get_stock_snapshot"],
             evidence_any=["분석", "요약", "Kakao", "카카오"]),
    EvalCase(12, "네이버 주가 흐름 어때?", "snapshot",
             tools_required=["get_stock_snapshot"],
             evidence_any=["NAVER", "네이버"]),
    # 비교 — snapshot 두 번
    EvalCase(13, "AAPL과 MSFT 중에 뭐가 나아?", "compare",
             tools_required=["get_stock_snapshot"],
             evidence_any=["Apple", "Microsoft", "AAPL", "MSFT"],
             note="snapshot 두 번 호출 기대 (최소 1번 이상)"),
    EvalCase(14, "삼성전자랑 SK하이닉스 비교해줘", "compare",
             tools_required=["get_stock_snapshot"],
             evidence_any=["삼성", "SK", "하이닉스"]),
    # 검색
    EvalCase(15, "코스피 종목 뭐있어?", "search",
             tools_required=["search_stocks"],
             evidence_any=["KRX", "코스피", "종목", "삼성", "SK", "카카오", "네이버"]),
    # 모호 — 종목명만
    EvalCase(16, "엔비디아", "snapshot",
             tools_required=[],  # snapshot or search; 어쨌든 시도 권장. 없으면 안내
             tools_forbidden=[],
             evidence_any=["엔비디아", "NVDA", "찾을 수 없", "DB", "검색"],
             note="DB에 없는 종목 → graceful 안내"),
    # 인사/잡담 — tool 호출 없어야
    EvalCase(17, "안녕!", "chat",
             tools_required=[],
             tools_forbidden=["get_stock_snapshot", "get_recent_news", "search_stocks"],
             evidence_any=["안녕", "도움", "주식", "종목"]),
    EvalCase(18, "넌 누구야?", "chat",
             tools_required=[],
             tools_forbidden=["get_stock_snapshot", "get_recent_news", "search_stocks"],
             evidence_any=["StockInsight", "주식", "어드바이저", "도와"]),
    # 일반 투자 조언 — tool 호출 없거나 search 정도
    EvalCase(19, "주식 투자 처음인데 뭘 봐야 해?", "chat",
             tools_required=[],
             tools_forbidden=["get_stock_snapshot", "get_recent_news"],
             evidence_any=["재무", "PER", "분석", "투자", "기초"],
             note="일반 조언 — tool 안 써도 OK"),
    # 뉴스 + 분석 혼합
    EvalCase(20, "삼성전자 최근 뉴스랑 같이 어떤지 알려줘", "mixed",
             tools_required=["get_stock_snapshot", "get_recent_news"],
             evidence_any=["삼성", "뉴스", "기사"],
             note="snapshot + news 둘 다 호출 기대"),
]


@dataclass
class CaseResult:
    case: EvalCase
    tools_called: list[str]
    answer: str
    tool_match: bool
    evidence_match: bool
    error: str = ""

    @property
    def passed(self) -> bool:
        return not self.error and self.tool_match and self.evidence_match


async def cleanup_eval_rows() -> int:
    async with async_session() as db:
        result = await db.execute(
            delete(ChatMessage).where(ChatMessage.user_id == EVAL_USER_ID)
        )
        await db.commit()
        return result.rowcount or 0


async def run_case(case: EvalCase) -> CaseResult:
    adapter = get_adapter()
    thread_id = uuid4()
    tools_called: list[str] = []
    answer_parts: list[str] = []
    err = ""

    try:
        async for ev in stream_chat(
            adapter=adapter,
            thread_id=thread_id,
            user_id=EVAL_USER_ID,
            user_message=case.question,
        ):
            ev_type = ev["event"]
            data = ev["data"]
            if ev_type == "token":
                answer_parts.append(data.get("content", ""))
            elif ev_type == "tool_call":
                tools_called.append(data.get("tool", ""))
            elif ev_type == "error":
                err = data.get("error", "unknown")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"

    answer = "".join(answer_parts)

    # tool_match: 모든 required tool 이 호출되었고, forbidden 은 하나도 없어야
    tool_match = all(t in tools_called for t in case.tools_required) and not any(
        t in tools_called for t in case.tools_forbidden
    )
    # evidence_match: any 에서 최소 1개 존재 (case-insensitive substring)
    if not case.evidence_any:
        evidence_match = True
    else:
        ans_lower = answer.lower()
        evidence_match = any(kw.lower() in ans_lower for kw in case.evidence_any)

    return CaseResult(
        case=case,
        tools_called=tools_called,
        answer=answer,
        tool_match=tool_match,
        evidence_match=evidence_match,
        error=err,
    )


def render_report(results: list[CaseResult]) -> str:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    tool_pass = sum(1 for r in results if r.tool_match and not r.error)
    ev_pass = sum(1 for r in results if r.evidence_match and not r.error)
    err_count = sum(1 for r in results if r.error)

    pct = lambda n: f"{n}/{total} ({100 * n // total}%)"

    lines = [
        f"# Phase A — Korean Tool-Selection Eval",
        "",
        f"- Run at: {datetime.now(timezone.utc).isoformat()}",
        f"- Cases: {total}",
        f"- **Passed: {pct(passed)}** (ship gate ≥ 80%)",
        f"- Tool match: {pct(tool_pass)}",
        f"- Evidence match: {pct(ev_pass)}",
        f"- Errors: {err_count}",
        "",
        "## Per-case results",
        "",
        "| # | Category | Question | Expected tools | Called | Tool✓ | Ev✓ | Pass |",
        "|---|----------|----------|----------------|--------|-------|-----|------|",
    ]
    for r in results:
        c = r.case
        expected = ", ".join(c.tools_required) or "(none)"
        called = ", ".join(r.tools_called) or "(none)"
        if c.tools_forbidden:
            expected += f" / no {','.join(c.tools_forbidden)}"
        q = c.question.replace("|", "\\|")
        lines.append(
            f"| {c.id} | {c.category} | {q} | {expected} | {called} | "
            f"{'✓' if r.tool_match else '✗'} | "
            f"{'✓' if r.evidence_match else '✗'} | "
            f"{'PASS' if r.passed else 'FAIL'} |"
        )

    lines.append("")
    lines.append("## Failures (detail)")
    lines.append("")
    any_fail = False
    for r in results:
        if r.passed:
            continue
        any_fail = True
        c = r.case
        lines.append(f"### #{c.id} [{c.category}] {c.question}")
        lines.append(f"- Expected tools: `{c.tools_required}`  forbidden: `{c.tools_forbidden}`")
        lines.append(f"- Called: `{r.tools_called}`")
        lines.append(f"- Evidence any: `{c.evidence_any}`")
        if r.error:
            lines.append(f"- Error: `{r.error}`")
        if c.note:
            lines.append(f"- Note: {c.note}")
        snippet = (r.answer or "").strip().replace("\n", " ")
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        lines.append(f"- Answer: {snippet or '(empty)'}")
        lines.append("")
    if not any_fail:
        lines.append("_(none)_")

    return "\n".join(lines)


async def main() -> int:
    deleted = await cleanup_eval_rows()
    print(f"Cleaned {deleted} prior eval rows.")

    results: list[CaseResult] = []
    for case in CASES:
        print(f"[{case.id:2d}/{len(CASES)}] {case.question}")
        try:
            r = await run_case(case)
        except Exception as e:
            r = CaseResult(case=case, tools_called=[], answer="",
                           tool_match=False, evidence_match=False,
                           error=f"{type(e).__name__}: {e}")
        results.append(r)
        flag = "PASS" if r.passed else "FAIL"
        print(f"     -> {flag}  tools={r.tools_called}  err={r.error or '-'}")

    report = render_report(results)
    out_dir = Path(__file__).resolve().parents[2] / "docs" / "gstack"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"phase-a-eval-{ts}.md"
    out_path.write_text(report, encoding="utf-8")

    print(f"\nReport written: {out_path}")
    passed = sum(1 for r in results if r.passed)
    pct = 100 * passed // len(results)
    # ASCII-only to avoid Windows cp949 console crash.
    print(f"Passed: {passed}/{len(results)} ({pct}%) - ship gate >= 80%")

    # Cleanup again so the DB doesn't keep eval traffic.
    await cleanup_eval_rows()

    return 0 if pct >= 80 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
