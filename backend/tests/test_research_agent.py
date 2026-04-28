"""Stage 1 research agent tests with a mocked adapter.

The real adapter's `chat_with_tools` is an async generator yielding event dicts
({"type": "text"|"function_call"|"done", ...}). Tests mock that shape.
"""
from typing import Any

import pytest

from app.services.analyst.research import run_research


class _FakeAdapter:
    """Adapter stub. Each call to `chat_with_tools` returns the next scripted stream."""

    def __init__(self, scripts: list[list[dict[str, Any]]]):
        self._scripts = list(scripts)
        self.calls = 0

    def chat_with_tools(self, messages, tools):
        self.calls += 1
        if not self._scripts:
            stream = [{"type": "done"}]
        else:
            stream = self._scripts.pop(0)
        return self._gen(stream)

    async def _gen(self, stream):
        for evt in stream:
            yield evt


@pytest.mark.asyncio
async def test_research_no_tool_calls_returns_findings(monkeypatch):
    """Adapter returns final JSON in first round → run returns parsed dict."""
    adapter = _FakeAdapter(
        [
            [
                {"type": "text", "content": '{"findings":[{"k":"v"}],"citations":[],"gaps_noted":[]}'},
                {"type": "done"},
            ]
        ]
    )
    monkeypatch.setattr("app.services.analyst.research.get_analyst_adapter", lambda: adapter)

    out = await run_research(ticker="005930", max_rounds=10)
    assert out["findings"] == [{"k": "v"}]
    assert out["researcher_version"] == "researcher_v1"
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_research_dispatches_tool_then_returns(monkeypatch):
    """Round 1: function_call → dispatcher returns dict. Round 2: final JSON."""
    adapter = _FakeAdapter(
        [
            [
                {
                    "type": "function_call",
                    "name": "get_indicators",
                    "arguments": {"ticker": "005930"},
                    "call_id": "c1",
                },
                {"type": "done"},
            ],
            [
                {"type": "text", "content": '{"findings":[{"rsi":58}],"citations":[],"gaps_noted":[]}'},
                {"type": "done"},
            ],
        ]
    )
    monkeypatch.setattr("app.services.analyst.research.get_analyst_adapter", lambda: adapter)
    monkeypatch.setattr(
        "app.services.analyst.research.dispatch_research_tool",
        _make_async_return({"rsi_14": 58}),
    )

    out = await run_research(ticker="005930", max_rounds=5)
    assert out["findings"] == [{"rsi": 58}]
    assert out["rounds_used"] == 2


@pytest.mark.asyncio
async def test_research_caps_rounds(monkeypatch):
    """LLM keeps calling a tool — orchestrator stops at max_rounds and forces final."""
    # Every round yields a function_call (loops forever without cap).
    looping_round = [
        {
            "type": "function_call",
            "name": "get_indicators",
            "arguments": {"ticker": "005930"},
            "call_id": "c1",
        },
        {"type": "done"},
    ]
    final_round = [
        {"type": "text", "content": '{"findings":[]}'},
        {"type": "done"},
    ]
    # max_rounds=3 → 3 looping rounds + 1 forced final = 4 calls
    adapter = _FakeAdapter([looping_round, looping_round, looping_round, final_round])
    monkeypatch.setattr("app.services.analyst.research.get_analyst_adapter", lambda: adapter)
    monkeypatch.setattr(
        "app.services.analyst.research.dispatch_research_tool",
        _make_async_return({"rsi_14": 58}),
    )

    out = await run_research(ticker="005930", max_rounds=3)
    assert out.get("max_rounds_hit") is True
    assert out["rounds_used"] == 3
    assert adapter.calls == 4  # 3 main + 1 forced flush


def _make_async_return(value):
    async def _fn(*args, **kwargs):
        return value

    return _fn
