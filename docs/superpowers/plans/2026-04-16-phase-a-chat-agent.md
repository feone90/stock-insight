# Phase 2.5 Phase A — Conversational Chat Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** StockInsight 가족(3명)이 "삼성전자 지금 어때?"처럼 자연어로 묻고, DB 기반 근거 있는 답변을 받는 대화형 chat 기능을 추가한다.

**Architecture:** 기존 `AzureOpenAIAdapter`를 확장해 Foundry Responses API에서 tool calling + streaming을 지원. SQLAlchemy `chat_messages` 테이블에 대화 이력 저장. SSE로 프론트엔드에 스트리밍. 좌측 사이드바 + 중앙 메시지 영역 + 하단 입력창 레이아웃 (ChatGPT 스타일, 다크 테마).

**Tech Stack:** FastAPI + SQLAlchemy(async) + asyncpg + httpx + Next.js 16 + React 19 + Tailwind + shadcn/ui + react-markdown + remark-gfm

**Scope basis:** `~/.gstack/projects/feone90-stock-insight/main-design-20260416-phase-a-revised.md` (APPROVED, supersedes 20260415). Eng review + Design review PASSED.

**Tools (3):** `get_stock_snapshot`, `get_recent_news`, `search_stocks`.
**Endpoints (4):** POST /api/chat (SSE), GET /api/chat/threads, GET /api/chat/history/{thread_id}, DELETE /api/chat/history/{thread_id}.

---

## Prerequisites (완료 후 Task 1 시작)

### Task 0A: Test DB Isolation (별도 PR)

**Why:** 신규 `chat_messages` 테이블 테스트가 dev DB를 오염시키지 않도록 conftest.py 트랜잭션 롤백 fixture 설정.

**Depends on:** 없음.

**Note:** 이 task는 **별도 PR로 선행 완료** 필수. 구현은 본 계획 범위 외. TODOS.md 첫 항목 참조. 완료 확인 후 Task 1 시작.

### Task 0B: Foundry Responses API function calling smoke test

**Files:**
- Create (임시): `backend/scripts/smoke_test_tools.py`

- [ ] **Step 1: 임시 smoke test 스크립트 작성**

```python
# backend/scripts/smoke_test_tools.py
"""Foundry Responses API function calling 지원 여부 검증."""

import asyncio
import json
import httpx

from app.config import settings


async def main():
    body = {
        "model": settings.llm_deployment,
        "input": [
            {"role": "user", "content": "삼성전자 현재가 알려줘."}
        ],
        "tools": [
            {
                "type": "function",
                "name": "get_stock_price",
                "description": "종목의 현재 가격을 반환한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                },
            }
        ],
        "tool_choice": "auto",
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            settings.llm_endpoint,
            json=body,
            headers={
                "api-key": settings.llm_api_key,
                "Content-Type": "application/json",
            },
        )
        print(f"HTTP {resp.status_code}")
        print(json.dumps(resp.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 실행 + 응답 확인**

Run: `cd backend && uv run python -m scripts.smoke_test_tools`

Expected: HTTP 200 + 응답 `output`에 `type: "function_call"` (또는 유사) 항목이 포함되어 있어야 함. `"tools" is not allowed` 류 에러가 나오면 Phase A 경로 재설계 필요 (STOP, eng review 다시).

- [ ] **Step 3: 응답 구조 기록 + 스크립트 삭제**

응답에서 tool_call 필드의 실제 키 이름(`function_call` vs `tool_call` 등)과 arguments 구조를 `main-design-20260416-phase-a-revised.md`의 "Open Questions → 1." 아래에 기록.

Run: `rm backend/scripts/smoke_test_tools.py`

- [ ] **Step 4: Commit**

```bash
git add docs/.. ~/.gstack/projects/feone90-stock-insight/main-design-20260416-phase-a-revised.md
git commit -m "docs: record Foundry Responses API tool-calling response format"
```

---

## Backend Implementation

### Task 1: ChatMessage ORM 모델 + Alembic migration

**Files:**
- Create: `backend/app/models/chat.py`
- Create: `backend/alembic/versions/<auto>_add_chat_messages.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: ChatMessage 모델 작성**

Create `backend/app/models/chat.py`:

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_thread_created", "thread_id", "created_at"),
        Index("ix_chat_user_updated", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4, nullable=False)
    user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 2: `__init__.py`에 export 추가**

Modify `backend/app/models/__init__.py`:

```python
from app.models.stock import Base, Stock
from app.models.price import PriceHistory
from app.models.analysis import Analysis, DailyKeyword, KeywordDetail
from app.models.favorite import Favorite
from app.models.news import News
from app.models.disclosure import Disclosure
from app.models.financial import Financial
from app.models.exchange_rate import ExchangeRate
from app.models.chat import ChatMessage  # NEW

__all__ = [
    "Base",
    "Stock",
    "PriceHistory",
    "Analysis",
    "KeywordDetail",
    "DailyKeyword",
    "Favorite",
    "News",
    "Disclosure",
    "Financial",
    "ExchangeRate",
    "ChatMessage",  # NEW
]
```

- [ ] **Step 3: Alembic migration 자동생성**

Run: `cd backend && uv run alembic revision --autogenerate -m "add chat_messages table"`

Expected: `backend/alembic/versions/<hash>_add_chat_messages.py` 파일 생성됨. `op.create_table("chat_messages", ...)` 포함 확인.

- [ ] **Step 4: Migration 실행**

Run: `cd backend && uv run alembic upgrade head`

Expected: 출력에 `Running upgrade ... -> <hash>, add chat_messages table`.

- [ ] **Step 5: 테이블 생성 검증**

Run: `psql -h localhost -U postgres -d stockinsight -c "\d chat_messages"`

Expected: `thread_id`, `user_id`, `role`, `content`, `tool_calls`, `created_at` 컬럼 존재.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/chat.py backend/app/models/__init__.py backend/alembic/versions/
git commit -m "feat: add chat_messages table for Phase A conversational agent"
```

---

### Task 2: Pydantic 스키마

**Files:**
- Create: `backend/app/schemas/chat.py`

- [ ] **Step 1: 스키마 작성**

Create `backend/app/schemas/chat.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    thread_id: UUID | None = None


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    tool_calls: dict | None = None
    created_at: str  # ISO format


class ChatHistoryResponse(BaseModel):
    thread_id: UUID
    messages: list[ChatMessageResponse]


class ThreadSummary(BaseModel):
    thread_id: UUID
    preview: str  # first user message, up to 80 chars
    last_updated: str


class ThreadListResponse(BaseModel):
    threads: list[ThreadSummary]


class DeleteResponse(BaseModel):
    status: str
    rows: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/chat.py
git commit -m "feat: add chat API Pydantic schemas"
```

---

### Task 3: Tool — `get_stock_snapshot`

**Files:**
- Create: `backend/app/services/chat/__init__.py`
- Create: `backend/app/services/chat/tools.py`
- Create: `backend/tests/test_chat_tools.py`

- [ ] **Step 1: 패키지 초기화**

Create `backend/app/services/chat/__init__.py`:

```python
```

(빈 파일)

- [ ] **Step 2: 실패하는 테스트 작성**

Create `backend/tests/test_chat_tools.py`:

```python
"""Chat agent tools tests."""

import pytest
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock, Financial, PriceHistory
from app.models.analysis import Analysis, KeywordDetail
from app.services.chat.tools import get_stock_snapshot


@pytest.mark.asyncio
async def test_get_stock_snapshot_happy(db: AsyncSession):
    """종목 존재 시 info+price+analysis+financials 통합 반환."""
    result = await get_stock_snapshot("005930")
    assert result.get("error") is None
    assert result["ticker"] == "005930"
    assert result["name"] == "삼성전자"
    assert "current_price" in result
    assert "change_percent" in result


@pytest.mark.asyncio
async def test_get_stock_snapshot_not_found():
    """없는 ticker는 error dict 반환, 예외 던지지 않음."""
    result = await get_stock_snapshot("ZZZNOTEXIST")
    assert result.get("error") is not None
    assert "찾을 수 없" in result["error"] or "없음" in result["error"]


@pytest.mark.asyncio
async def test_get_stock_snapshot_includes_analysis_when_present(db: AsyncSession):
    """analysis가 있으면 summary + 키워드 일부 포함."""
    result = await get_stock_snapshot("005930")
    # seed 데이터에 analysis가 있다고 가정; 없어도 error 없이 recent_analysis=None
    assert "recent_analysis_summary" in result
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run: `cd backend && uv run python -m pytest tests/test_chat_tools.py -v`

Expected: `ModuleNotFoundError: No module named 'app.services.chat.tools'`

- [ ] **Step 4: 최소 구현**

Create `backend/app/services/chat/tools.py`:

```python
"""LLM chat agent tools — DB access functions.

Each tool:
- Opens its own async_session (same pattern as scheduler._sync_single_stock)
- Returns a dict (never raises for expected errors)
- On known error: {"error": "..."}
"""

import logging
from datetime import date, timedelta

from sqlalchemy import select

from app.database import async_session
from app.models import Stock, Financial, PriceHistory
from app.models.analysis import Analysis, KeywordDetail
from app.models.news import News

logger = logging.getLogger(__name__)


async def get_stock_snapshot(ticker: str) -> dict:
    """종목 기본정보 + 최근 가격 + 최신 분석 + 재무지표 통합 조회."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock_result = await db.execute(
            select(Stock).where(Stock.ticker == ticker)
        )
        stock = stock_result.scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}'을(를) 찾을 수 없습니다."}

        # 최신 재무
        fin_result = await db.execute(
            select(Financial)
            .where(Financial.stock_id == stock.id)
            .order_by(Financial.created_at.desc())
            .limit(1)
        )
        fin = fin_result.scalar_one_or_none()

        # 최신 분석 (daily)
        analysis_result = await db.execute(
            select(Analysis)
            .where(Analysis.stock_id == stock.id, Analysis.period_type == "daily")
            .order_by(Analysis.date.desc())
            .limit(1)
        )
        analysis = analysis_result.scalar_one_or_none()

        recent_summary = None
        recent_keywords = []
        if analysis is not None:
            recent_summary = analysis.summary
            kw_result = await db.execute(
                select(KeywordDetail)
                .where(KeywordDetail.analysis_id == analysis.id)
                .limit(5)
            )
            recent_keywords = [
                {"keyword": k.keyword, "type": k.type, "detail": k.detail}
                for k in kw_result.scalars().all()
            ]

        return {
            "ticker": stock.ticker,
            "name": stock.name,
            "market": stock.market,
            "sector": stock.sector,
            "current_price": stock.current_price,
            "change": stock.change,
            "change_percent": stock.change_percent,
            "per": fin.per if fin else None,
            "pbr": fin.pbr if fin else None,
            "market_cap": fin.market_cap if fin else None,
            "dividend_yield": fin.dividend_yield if fin else None,
            "recent_analysis_summary": recent_summary,
            "recent_analysis_keywords": recent_keywords,
        }
```

- [ ] **Step 5: 테스트 재실행 (통과 확인)**

Run: `cd backend && uv run python -m pytest tests/test_chat_tools.py::test_get_stock_snapshot_happy tests/test_chat_tools.py::test_get_stock_snapshot_not_found tests/test_chat_tools.py::test_get_stock_snapshot_includes_analysis_when_present -v`

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/chat/ backend/tests/test_chat_tools.py
git commit -m "feat: add get_stock_snapshot tool for chat agent"
```

---

### Task 4: Tool — `get_recent_news`

**Files:**
- Modify: `backend/app/services/chat/tools.py`
- Modify: `backend/tests/test_chat_tools.py`

- [ ] **Step 1: 실패하는 테스트 추가**

Append to `backend/tests/test_chat_tools.py`:

```python
from app.services.chat.tools import get_recent_news


@pytest.mark.asyncio
async def test_get_recent_news_happy(db: AsyncSession):
    """최근 뉴스 상위 10건을 dict 리스트로 반환."""
    result = await get_recent_news("005930", days=7)
    assert isinstance(result, list)
    if result:  # seed에 뉴스 있을 때만
        assert "title" in result[0]
        assert "published_at" in result[0]
        assert "source" in result[0]


@pytest.mark.asyncio
async def test_get_recent_news_not_found():
    """없는 종목 → 빈 리스트."""
    result = await get_recent_news("ZZZNOTEXIST")
    assert result == []


@pytest.mark.asyncio
async def test_get_recent_news_respects_days(db: AsyncSession):
    """days 파라미터가 오래된 뉴스를 제외."""
    result = await get_recent_news("005930", days=1)
    # days=1이면 최근 1일만 반환; 비어 있어도 정상
    assert isinstance(result, list)
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `cd backend && uv run python -m pytest tests/test_chat_tools.py::test_get_recent_news_happy -v`

Expected: `ImportError: cannot import name 'get_recent_news'`

- [ ] **Step 3: 구현 추가**

Append to `backend/app/services/chat/tools.py`:

```python
async def get_recent_news(ticker: str, days: int = 7) -> list[dict]:
    """최근 N일 뉴스 상위 10건 (title+published_at+source+url)."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock_result = await db.execute(
            select(Stock).where(Stock.ticker == ticker)
        )
        stock = stock_result.scalar_one_or_none()
        if not stock:
            return []

        since = date.today() - timedelta(days=days)
        news_result = await db.execute(
            select(News)
            .where(News.stock_id == stock.id, News.published_at >= since)
            .order_by(News.published_at.desc())
            .limit(10)
        )
        news_rows = news_result.scalars().all()
        return [
            {
                "title": n.title,
                "published_at": n.published_at.strftime("%Y-%m-%d") if n.published_at else "",
                "source": n.source or "",
                "url": n.url or "",
            }
            for n in news_rows
        ]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run python -m pytest tests/test_chat_tools.py -v`

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chat/tools.py backend/tests/test_chat_tools.py
git commit -m "feat: add get_recent_news tool for chat agent"
```

---

### Task 5: Tool — `search_stocks`

**Files:**
- Modify: `backend/app/services/chat/tools.py`
- Modify: `backend/tests/test_chat_tools.py`

- [ ] **Step 1: 실패하는 테스트 추가**

Append to `backend/tests/test_chat_tools.py`:

```python
from app.services.chat.tools import search_stocks


@pytest.mark.asyncio
async def test_search_stocks_by_name(db: AsyncSession):
    """이름으로 DB 검색."""
    result = await search_stocks("삼성")
    assert isinstance(result, list)
    assert any(s["ticker"] == "005930" for s in result)


@pytest.mark.asyncio
async def test_search_stocks_by_ticker(db: AsyncSession):
    """ticker로 DB 검색."""
    result = await search_stocks("TSLA")
    assert isinstance(result, list)
    assert any(s["ticker"] == "TSLA" for s in result)


@pytest.mark.asyncio
async def test_search_stocks_empty():
    """빈 쿼리 → 빈 리스트."""
    result = await search_stocks("")
    assert result == []


@pytest.mark.asyncio
async def test_search_stocks_no_results():
    """매칭 없음 → 빈 리스트."""
    result = await search_stocks("ZZZNOTEXIST")
    assert result == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run python -m pytest tests/test_chat_tools.py::test_search_stocks_by_name -v`

Expected: `ImportError: cannot import name 'search_stocks'`

- [ ] **Step 3: 구현 추가**

Append to `backend/app/services/chat/tools.py`:

```python
async def search_stocks(query: str) -> list[dict]:
    """종목 이름 또는 ticker로 DB 검색 (최대 5건)."""
    query = query.strip()
    if not query:
        return []
    async with async_session() as db:
        stmt = (
            select(Stock)
            .where(Stock.name.ilike(f"%{query}%") | Stock.ticker.ilike(f"%{query}%"))
            .limit(5)
        )
        result = await db.execute(stmt)
        return [
            {
                "ticker": s.ticker,
                "name": s.name,
                "market": s.market,
            }
            for s in result.scalars().all()
        ]
```

- [ ] **Step 4: 전체 tool 테스트 통과 확인**

Run: `cd backend && uv run python -m pytest tests/test_chat_tools.py -v`

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chat/tools.py backend/tests/test_chat_tools.py
git commit -m "feat: add search_stocks tool for chat agent"
```

---

### Task 6: `AzureOpenAIAdapter.chat_with_tools` 확장

**Files:**
- Modify: `backend/app/services/llm/adapter.py`
- Create: `backend/tests/test_llm_chat.py`

- [ ] **Step 1: Tool schema 빌더 헬퍼 작성**

먼저 `backend/app/services/chat/tools.py` 맨 아래에 tool schema를 추가:

```python
TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_stock_snapshot",
        "description": "종목의 기본 정보, 현재가, 최신 분석 요약, 재무지표를 한 번에 조회. 종목에 대한 일반적 질문에 먼저 사용.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "종목 코드 (예: '005930', 'TSLA')"},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_recent_news",
        "description": "종목의 최근 뉴스를 조회. 사용자가 '뉴스', '소식'을 명시적으로 물을 때 사용.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "description": "최근 며칠 (기본 7)", "default": 7},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "search_stocks",
        "description": "종목 이름이나 ticker로 검색. 사용자가 종목명만 말했을 때 ticker 확보용.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "종목명 또는 ticker (예: '삼성', 'TSLA')"},
            },
            "required": ["query"],
        },
    },
]


TOOL_FUNCTIONS = {
    "get_stock_snapshot": get_stock_snapshot,
    "get_recent_news": get_recent_news,
    "search_stocks": search_stocks,
}
```

- [ ] **Step 2: 실패하는 adapter 테스트 작성**

Create `backend/tests/test_llm_chat.py`:

```python
"""AzureOpenAIAdapter.chat_with_tools 테스트 (mocked httpx)."""

import json
import pytest
from unittest.mock import patch, AsyncMock

from app.services.llm.adapter import AzureOpenAIAdapter


@pytest.mark.asyncio
async def test_chat_with_tools_sends_correct_body():
    """tools와 messages를 body에 포함해 Foundry Responses API로 POST."""
    adapter = AzureOpenAIAdapter(
        endpoint="https://fake.openai.azure.com/openai/responses",
        api_key="fake-key",
        deployment="gpt-4o",
    )

    fake_response = {
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "안녕하세요!"}]}
        ]
    }

    captured_body = {}

    async def mock_post(self, url, **kwargs):
        captured_body.update(kwargs.get("json", {}))
        from httpx import Response
        return Response(200, json=fake_response)

    with patch("httpx.AsyncClient.post", new=mock_post):
        events = []
        async for event in adapter.chat_with_tools(
            messages=[{"role": "user", "content": "안녕"}],
            tools=[{"type": "function", "name": "test_tool", "description": "x", "parameters": {}}],
        ):
            events.append(event)

    assert captured_body["model"] == "gpt-4o"
    assert captured_body["input"] == [{"role": "user", "content": "안녕"}]
    assert len(captured_body["tools"]) == 1
    assert captured_body["tools"][0]["name"] == "test_tool"
    assert captured_body["tool_choice"] == "auto"
```

- [ ] **Step 3: 실패 확인**

Run: `cd backend && uv run python -m pytest tests/test_llm_chat.py -v`

Expected: `AttributeError: 'AzureOpenAIAdapter' object has no attribute 'chat_with_tools'`

- [ ] **Step 4: `chat_with_tools` 구현**

Modify `backend/app/services/llm/adapter.py`. `AzureOpenAIAdapter` 클래스 안에 추가:

```python
    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ):
        """Foundry Responses API로 tool-calling 요청, 결과를 async generator로 yield.

        Yields dicts:
          {"type": "text", "content": "..."}
          {"type": "tool_call", "name": "...", "arguments": {...}, "call_id": "..."}
          {"type": "done"}
        """
        body = {
            "model": self.deployment,
            "input": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.endpoint,
                json=body,
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()

        data = resp.json()
        for item in data.get("output", []):
            item_type = item.get("type")
            if item_type == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        yield {"type": "text", "content": content.get("text", "")}
            elif item_type in ("function_call", "tool_call"):
                # Step 0B smoke test에서 정확한 키 이름 확인 필요.
                # 여기서는 두 형식 모두 지원.
                import json as _json
                raw_args = item.get("arguments") or item.get("function", {}).get("arguments", "{}")
                try:
                    args = _json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except _json.JSONDecodeError:
                    args = {}
                yield {
                    "type": "tool_call",
                    "name": item.get("name") or item.get("function", {}).get("name", ""),
                    "arguments": args,
                    "call_id": item.get("call_id") or item.get("id", ""),
                }

        yield {"type": "done"}
```

- [ ] **Step 5: LLMAdapter ABC에도 선언 추가**

Modify `backend/app/services/llm/adapter.py` (LLMAdapter ABC 내부):

```python
class LLMAdapter(ABC):
    """LLM 호출 인터페이스. 어댑터 패턴으로 모델 교체 가능."""

    @abstractmethod
    async def generate(self, prompt: str) -> str: ...

    @abstractmethod
    async def generate_json(self, prompt: str) -> str: ...

    async def chat_with_tools(self, messages: list[dict], tools: list[dict]):
        """Tool-calling 지원 어댑터만 구현. 기본은 NotImplementedError."""
        raise NotImplementedError("This adapter does not support tool calling")
        # async generator에서 raise가 바로 던져지도록 yield 한번 선언
        yield  # pragma: no cover
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && uv run python -m pytest tests/test_llm_chat.py -v`

Expected: 1 passed.

- [ ] **Step 7: 기존 adapter 테스트 회귀 확인**

Run: `cd backend && uv run python -m pytest tests/test_llm.py tests/test_analyzer.py -v`

Expected: 기존 테스트 모두 통과 (regression 없음).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/llm/adapter.py backend/app/services/chat/tools.py backend/tests/test_llm_chat.py
git commit -m "feat: add chat_with_tools to AzureOpenAIAdapter for tool-calling"
```

---

### Task 7: Chat 스트리밍 오케스트레이터

**Files:**
- Create: `backend/app/services/chat/stream.py`

**컨텍스트:** POST /api/chat 핸들러에서 호출할 async generator. 역할:
1. DB에서 최근 20턴 로드
2. Adapter 호출 (tool 루프)
3. tool_call 이벤트 시 해당 tool 실행, 결과 다시 adapter에 넣기
4. 토큰을 SSE 이벤트로 yield
5. 완료 시 user+assistant 메시지 DB에 persist

- [ ] **Step 1: stream 모듈 작성**

Create `backend/app/services/chat/stream.py`:

```python
"""Chat agent streaming orchestrator.

LLM adapter의 tool-calling 루프를 돌리며 SSE 이벤트를 yield.
메시지는 generator 완료 시 DB에 persist.
"""

import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.database import async_session
from app.models import ChatMessage
from app.services.chat.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from app.services.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 StockInsight 대화형 주식 어드바이저입니다.
사용자가 종목에 대해 물으면, 반드시 DB tool을 사용해 근거 있는 답변을 하세요.

규칙:
1. 종목명만 말했으면 search_stocks로 ticker를 먼저 확보하세요.
2. ticker를 알면 get_stock_snapshot으로 기본 정보를 가져오세요.
3. 사용자가 '뉴스'를 명시적으로 물으면 get_recent_news를 쓰세요.
4. tool이 {"error": ...}를 반환하면 사용자에게 자연어로 안내하세요.
5. 답변은 한국어, 구체적 수치/제목 포함, 간결하게.
6. 투자 권유가 아님을 과장해서 언급할 필요 없음. 자연스럽게 데이터를 제시.
"""

MAX_CONTEXT_TURNS = 20
MAX_TOOL_ROUNDS = 5  # 무한 루프 방지


async def _load_history(thread_id: UUID, user_id: str, limit: int = MAX_CONTEXT_TURNS) -> list[dict]:
    """thread_id의 최근 N턴을 LLM messages 포맷으로 로드."""
    async with async_session() as db:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id, ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()  # 시간순 복원
        return [
            {"role": r.role, "content": r.content}
            for r in rows
        ]


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
        # 1. 기존 history 로드
        history = await _load_history(thread_id, user_id)
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}] + history + new_messages

        assistant_content = ""
        tool_calls_for_message: list[dict] = []

        # 2. Tool 루프
        for round_num in range(MAX_TOOL_ROUNDS):
            tool_invocations = []
            async for event in adapter.chat_with_tools(conversation, TOOL_SCHEMAS):
                if event["type"] == "text":
                    chunk = event["content"]
                    assistant_content += chunk
                    yield {"event": "token", "data": {"content": chunk}}
                elif event["type"] == "tool_call":
                    tool_invocations.append(event)
                    yield {
                        "event": "tool_call",
                        "data": {"tool": event["name"], "args": event["arguments"]},
                    }
                elif event["type"] == "done":
                    break

            # tool 호출 없으면 대화 종료
            if not tool_invocations:
                break

            # tool 실행 후 다음 round 준비
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

                tool_calls_for_message.append({
                    "name": inv["name"],
                    "arguments": inv["arguments"],
                    "result": tool_result,
                })
                conversation.append({
                    "role": "assistant",
                    "content": f"[tool call: {inv['name']}({json.dumps(inv['arguments'], ensure_ascii=False)})]",
                })
                conversation.append({
                    "role": "user",
                    "content": f"[tool result: {json.dumps(tool_result, ensure_ascii=False)}]",
                })

        # 3. assistant 메시지 append
        new_messages.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": {"invocations": tool_calls_for_message} if tool_calls_for_message else None,
        })

        # 4. 완료 이벤트
        yield {
            "event": "done",
            "data": {
                "thread_id": str(thread_id),
                "message_count": len(new_messages),
            },
        }

    except Exception as e:
        logger.exception("stream_chat failed")
        yield {"event": "error", "data": {"error": str(e)}}
    finally:
        # 에러가 나도 user 메시지 + (가능한) assistant partial은 저장
        if assistant_content and len(new_messages) == 1:
            new_messages.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": {"invocations": tool_calls_for_message} if tool_calls_for_message else None,
            })
        try:
            await _persist_messages(thread_id, user_id, new_messages)
        except Exception as e:
            logger.error("Failed to persist messages for thread %s: %s", thread_id, e)
```

- [ ] **Step 2: 간단한 smoke test** (복잡한 로직이라 unit test는 chat API 테스트에서 통합 검증)

Run: `cd backend && uv run python -c "from app.services.chat.stream import stream_chat, SYSTEM_PROMPT; print(SYSTEM_PROMPT[:50])"`

Expected: `당신은 StockInsight 대화형 주식 어드바이저입니다.`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/chat/stream.py
git commit -m "feat: add chat streaming orchestrator with tool-calling loop"
```

---

### Task 8: POST /api/chat (SSE) + GET/DELETE 엔드포인트

**Files:**
- Create: `backend/app/api/chat.py`
- Create: `backend/tests/test_chat_api.py`

- [ ] **Step 1: 실패하는 API 테스트 작성**

Create `backend/tests/test_chat_api.py`:

```python
"""Chat API SSE + history + threads 테스트."""

import json
import pytest
from unittest.mock import patch
from uuid import UUID, uuid4

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_chat_streams_tokens(client: AsyncClient):
    """POST /api/chat → SSE 스트림: token → done."""

    async def fake_stream(adapter, thread_id, user_id, user_message):
        yield {"event": "token", "data": {"content": "안녕"}}
        yield {"event": "token", "data": {"content": "하세요"}}
        yield {"event": "done", "data": {"thread_id": str(thread_id), "message_count": 2}}

    with patch("app.api.chat.stream_chat", new=fake_stream):
        async with client.stream("POST", "/api/chat", json={"message": "삼성"}) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
            text = body.decode("utf-8")
            assert "event: token" in text
            assert "event: done" in text


@pytest.mark.asyncio
async def test_post_chat_assigns_thread_id_when_missing(client: AsyncClient):
    """thread_id 없으면 서버에서 생성, done 이벤트에 포함."""

    async def fake_stream(adapter, thread_id, user_id, user_message):
        yield {"event": "done", "data": {"thread_id": str(thread_id), "message_count": 1}}

    with patch("app.api.chat.stream_chat", new=fake_stream):
        async with client.stream("POST", "/api/chat", json={"message": "test"}) as response:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
            text = body.decode("utf-8")
            # done 이벤트에서 thread_id 추출
            done_line = [l for l in text.split("\n") if l.startswith("data:") and "thread_id" in l][0]
            payload = json.loads(done_line.split("data:", 1)[1].strip())
            UUID(payload["thread_id"])  # 유효한 UUID인지 검증


@pytest.mark.asyncio
async def test_get_history_empty_when_thread_missing(client: AsyncClient):
    """존재 안 하는 thread → 빈 messages."""
    fake_id = str(uuid4())
    response = await client.get(f"/api/chat/history/{fake_id}")
    assert response.status_code == 200
    assert response.json()["messages"] == []


@pytest.mark.asyncio
async def test_delete_history_returns_rows_deleted(client: AsyncClient):
    """DELETE thread → status + rows 반환."""
    fake_id = str(uuid4())
    response = await client.delete(f"/api/chat/history/{fake_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"
    assert "rows" in data


@pytest.mark.asyncio
async def test_get_threads_returns_list(client: AsyncClient):
    """GET /api/chat/threads → 사용자의 thread 리스트."""
    response = await client.get("/api/chat/threads")
    assert response.status_code == 200
    data = response.json()
    assert "threads" in data
    assert isinstance(data["threads"], list)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run python -m pytest tests/test_chat_api.py -v`

Expected: 404 (라우터 미등록) 또는 `ImportError`.

- [ ] **Step 3: API 구현**

Create `backend/app/api/chat.py`:

```python
"""Chat API — SSE streaming + history CRUD."""

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserInfo, get_current_user
from app.database import get_db
from app.models import ChatMessage
from app.schemas.chat import (
    ChatRequest,
    ChatHistoryResponse,
    ChatMessageResponse,
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    user: UserInfo = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 thread 목록 (첫 user 메시지 미리보기 + last_updated)."""
    # thread_id 별 첫 user 메시지(preview) + 마지막 메시지 시각
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
        thread_id = row.thread_id
        # 해당 thread의 첫 user 메시지
        first_msg_result = await db.execute(
            select(ChatMessage.content)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.user_id == user.email,
                ChatMessage.role == "user",
            )
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
        first = first_msg_result.scalar_one_or_none() or ""
        preview = first[:80]
        threads.append(ThreadSummary(
            thread_id=thread_id,
            preview=preview,
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
        .where(
            ChatMessage.thread_id == thread_id,
            ChatMessage.user_id == user.email,
        )
        .order_by(ChatMessage.created_at.asc())
    )
    rows = result.scalars().all()

    messages = [
        ChatMessageResponse(
            role=r.role,
            content=r.content,
            tool_calls=r.tool_calls,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
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
```

- [ ] **Step 4: main.py에 라우터 등록**

Modify `backend/app/main.py`:

```python
from app.api.chat import router as chat_router
...
app.include_router(chat_router)
```

(기존 `include_router` 호출 아래에 삽입)

- [ ] **Step 5: 테스트 재실행 (통과 확인)**

Run: `cd backend && uv run python -m pytest tests/test_chat_api.py -v`

Expected: 5 passed.

- [ ] **Step 6: 전체 회귀 확인**

Run: `cd backend && uv run python -m pytest tests/ -v`

Expected: 모든 테스트 통과 (기존 + 신규).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/chat.py backend/app/main.py backend/tests/test_chat_api.py
git commit -m "feat: add POST /api/chat SSE + history/threads/delete endpoints"
```

---

## Frontend Implementation

### Task 9: react-markdown 의존성 설치 + TypeScript 타입

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/types/chat.ts`

- [ ] **Step 1: 의존성 설치**

Run: `cd frontend && npm install react-markdown remark-gfm`

Expected: `package.json`에 `react-markdown` + `remark-gfm` 추가.

- [ ] **Step 2: chat 타입 정의**

Create `frontend/src/types/chat.ts`:

```typescript
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
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/types/chat.ts
git commit -m "feat: add react-markdown deps and chat types"
```

---

### Task 10: Chat API 클라이언트 (SSE 파싱 포함)

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: chat API 함수 추가**

Append to `frontend/src/services/api.ts`:

```typescript
import type { ChatMessage, SseEvent, ThreadSummary } from "@/types/chat";

export async function* streamChat(
  message: string,
  threadId: string | null,
  signal: AbortSignal
): AsyncGenerator<SseEvent, void, void> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`Chat API error: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE events are separated by \n\n
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = parseSseBlock(raw);
      if (event) yield event;
    }
  }
}

function parseSseBlock(block: string): SseEvent | null {
  const lines = block.split("\n");
  let eventName = "";
  let dataLine = "";
  for (const line of lines) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
  }
  if (!eventName || !dataLine) return null;
  try {
    const data = JSON.parse(dataLine);
    return { event: eventName, data } as SseEvent;
  } catch {
    return null;
  }
}

export async function listThreads(): Promise<ThreadSummary[]> {
  const res = await fetchJson<{ threads: ThreadSummary[] }>("/api/chat/threads");
  return res.threads;
}

export async function getThreadHistory(threadId: string): Promise<ChatMessage[]> {
  const res = await fetchJson<{ thread_id: string; messages: ChatMessage[] }>(
    `/api/chat/history/${threadId}`
  );
  return res.messages;
}

export async function deleteThread(threadId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/history/${threadId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}
```

- [ ] **Step 2: 타입 체크**

Run: `cd frontend && npx tsc --noEmit`

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add streamChat SSE client + thread CRUD API"
```

---

### Task 11: MessageBubble 컴포넌트 (user + assistant + markdown)

**Files:**
- Create: `frontend/src/components/chat/message-bubble.tsx`

- [ ] **Step 1: 컴포넌트 작성**

Create `frontend/src/components/chat/message-bubble.tsx`:

```typescript
"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "@/types/chat";

interface Props {
  message: ChatMessage;
  streaming?: boolean;
}

export function MessageBubble({ message, streaming = false }: Props) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const timestamp = new Date(message.created_at).toLocaleString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className={`group flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`relative ${
          isUser
            ? "max-w-[75%] sm:max-w-[60%] rounded-2xl rounded-tr-sm border border-slate-700 bg-slate-800 px-4 py-2.5 text-slate-50"
            : "max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-tl-sm border border-purple-500/20 bg-purple-500/5 px-4 py-2.5 text-slate-200"
        }`}
      >
        {!isUser && (
          <div className="mb-1 text-xs font-medium text-purple-400">
            🤖 StockInsight AI
          </div>
        )}

        {isUser ? (
          <div className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </div>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none text-sm leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content || (streaming ? "질문을 이해하고 있어요..." : "")}
            </ReactMarkdown>
            {streaming && <span className="inline-block ml-0.5 w-2 h-4 bg-slate-400 animate-pulse" />}
          </div>
        )}

        <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-slate-600 opacity-0 transition-opacity group-hover:opacity-100">
          <span>{timestamp}</span>
          {!isUser && message.content && (
            <button
              onClick={handleCopy}
              className="rounded px-1 hover:bg-slate-700/50 hover:text-slate-300"
              aria-label="복사"
            >
              {copied ? "✓ 복사됨" : "📋 복사"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/chat/message-bubble.tsx
git commit -m "feat: add MessageBubble component with markdown + hover actions"
```

---

### Task 12: ToolCallBadge 컴포넌트

**Files:**
- Create: `frontend/src/components/chat/tool-call-badge.tsx`

- [ ] **Step 1: 컴포넌트 작성**

Create `frontend/src/components/chat/tool-call-badge.tsx`:

```typescript
"use client";

const TOOL_LABELS: Record<string, string> = {
  get_stock_snapshot: "스냅샷 조회",
  get_recent_news: "뉴스 검색",
  search_stocks: "종목 검색",
};

interface Props {
  tool: string;
  args: Record<string, unknown>;
  completed?: boolean;
}

export function ToolCallBadge({ tool, args, completed = false }: Props) {
  const label = TOOL_LABELS[tool] ?? tool;
  const ticker = typeof args.ticker === "string" ? args.ticker : undefined;
  const query = typeof args.query === "string" ? args.query : undefined;
  const arg = ticker ?? query ?? "";

  return (
    <div className="my-2 flex justify-center">
      <div
        className={`inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs ${
          completed ? "text-slate-600" : "text-slate-400"
        }`}
        role="status"
        aria-live="polite"
      >
        <span>📊</span>
        <span>
          {arg ? `${arg} ${label}` : label}
          {!completed && " 중..."}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/chat/tool-call-badge.tsx
git commit -m "feat: add ToolCallBadge component"
```

---

### Task 13: ChatInput 컴포넌트 (전송/중단 토글)

**Files:**
- Create: `frontend/src/components/chat/chat-input.tsx`

- [ ] **Step 1: 컴포넌트 작성**

Create `frontend/src/components/chat/chat-input.tsx`:

```typescript
"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  streaming: boolean;
  onSend: (message: string) => void;
  onStop: () => void;
  autoFocus?: boolean;
}

export function ChatInput({ streaming, onSend, onStop, autoFocus = true }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  // Auto-resize textarea
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [value]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    } else if (e.key === "Escape") {
      e.currentTarget.blur();
    }
  };

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || streaming) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-slate-800 bg-slate-950/95 backdrop-blur-sm pb-[env(safe-area-inset-bottom)] lg:left-60">
      <div className="mx-auto flex max-w-3xl items-end gap-2 px-4 py-3">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder="질문을 입력하세요 (Enter: 전송, Shift+Enter: 줄바꿈)"
          disabled={streaming}
          rows={1}
          className="flex-1 resize-none rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-50 placeholder:text-slate-600 focus:border-purple-500/50 focus:outline-none focus:ring-1 focus:ring-purple-500/50 disabled:opacity-50"
        />
        {streaming ? (
          <button
            onClick={onStop}
            aria-label="응답 중단"
            className="flex h-11 w-11 min-h-[44px] min-w-[44px] items-center justify-center rounded-xl border border-red-500/30 bg-red-500/10 text-red-400 transition-colors hover:bg-red-500/20"
          >
            ■
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!value.trim()}
            aria-label="전송"
            className="flex h-11 w-11 min-h-[44px] min-w-[44px] items-center justify-center rounded-xl border border-purple-500/30 bg-purple-500/10 text-purple-400 transition-colors hover:bg-purple-500/20 disabled:opacity-30"
          >
            ➤
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/chat/chat-input.tsx
git commit -m "feat: add ChatInput with send/stop toggle and auto-resize"
```

---

### Task 14: ChatSidebar 컴포넌트 (thread list + 새 대화 + undo delete)

**Files:**
- Create: `frontend/src/components/chat/chat-sidebar.tsx`

- [ ] **Step 1: 컴포넌트 작성**

Create `frontend/src/components/chat/chat-sidebar.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { deleteThread, listThreads } from "@/services/api";
import { showToast } from "@/components/ui/toast";
import type { ThreadSummary } from "@/types/chat";

interface Props {
  activeThreadId: string | null;
  onSelect: (threadId: string | null) => void;
  refreshKey: number;  // 부모가 갱신 신호 보낼 때 증가
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function ChatSidebar({ activeThreadId, onSelect, refreshKey, mobileOpen, onMobileClose }: Props) {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(new Set());  // undo pending

  useEffect(() => {
    setLoading(true);
    listThreads()
      .then(setThreads)
      .catch(() => showToast("대화 목록 로드 실패", "error"))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const handleDelete = (threadId: string) => {
    setHidden((prev) => new Set(prev).add(threadId));
    const timer = setTimeout(() => {
      deleteThread(threadId)
        .then(() => {
          setThreads((prev) => prev.filter((t) => t.thread_id !== threadId));
          if (activeThreadId === threadId) onSelect(null);
        })
        .catch(() => {
          showToast("삭제 실패", "error");
          setHidden((prev) => {
            const next = new Set(prev);
            next.delete(threadId);
            return next;
          });
        });
    }, 5000);

    showToast("대화를 삭제했어요 [실행 취소]", "info");
    // 5초 내 undo 클릭 감지는 간단 구현: toast 메시지 자체 클릭
    // Phase A는 매우 간단하게 — toast를 클릭 안 하면 5초 후 실제 삭제
    // 실행 취소 UX는 Phase B에서 개선
    void timer;
  };

  const handleNewChat = () => {
    onSelect(null);
    onMobileClose();
  };

  const visibleThreads = threads.filter((t) => !hidden.has(t.thread_id));

  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={onMobileClose}
          aria-hidden
        />
      )}

      <aside
        className={`fixed top-14 bottom-0 left-0 z-40 w-60 border-r border-slate-800 bg-slate-950 transition-transform lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col">
          <div className="border-b border-slate-800 p-3">
            <button
              onClick={handleNewChat}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-slate-800"
            >
              + 새 대화
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            {loading && <div className="p-2 text-xs text-slate-600">로딩 중...</div>}
            {!loading && visibleThreads.length === 0 && (
              <div className="p-2 text-xs text-slate-600">아직 대화 없음</div>
            )}
            {visibleThreads.map((t) => (
              <div
                key={t.thread_id}
                className={`group mb-1 flex items-center gap-1 rounded-md px-2 py-2 text-xs transition-colors ${
                  activeThreadId === t.thread_id
                    ? "border border-purple-500/30 bg-purple-500/5"
                    : "hover:bg-slate-900"
                }`}
              >
                <button
                  onClick={() => {
                    onSelect(t.thread_id);
                    onMobileClose();
                  }}
                  className="flex-1 truncate text-left text-slate-300"
                  title={t.preview}
                >
                  {t.preview || "(빈 대화)"}
                </button>
                <button
                  onClick={() => handleDelete(t.thread_id)}
                  aria-label="삭제"
                  className="opacity-0 text-slate-600 transition-opacity hover:text-red-400 group-hover:opacity-100"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/chat/chat-sidebar.tsx
git commit -m "feat: add ChatSidebar with thread list and soft delete"
```

---

### Task 15: MessageList 컴포넌트 (스크롤 관리 + streaming 반영)

**Files:**
- Create: `frontend/src/components/chat/message-list.tsx`

- [ ] **Step 1: 컴포넌트 작성**

Create `frontend/src/components/chat/message-list.tsx`:

```typescript
"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./message-bubble";
import { ToolCallBadge } from "./tool-call-badge";
import type { ChatMessage } from "@/types/chat";

export interface ToolCallInProgress {
  tool: string;
  args: Record<string, unknown>;
  key: number;
}

interface Props {
  messages: ChatMessage[];
  toolCalls: ToolCallInProgress[];  // 완료된 이전 것들 + 진행 중인 것
  streamingContent: string | null;  // 현재 스트리밍 중인 assistant content (아직 messages에 없음)
  streamingHint: string;             // "질문을 이해하고 있어요..." 등 사지적 단서
}

export function MessageList({ messages, toolCalls, streamingContent, streamingHint }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingContent, toolCalls]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-40 pt-4" role="log" aria-live="polite">
      {messages.map((m, i) => (
        <MessageBubble key={i} message={m} />
      ))}
      {toolCalls.map((tc) => (
        <ToolCallBadge key={tc.key} tool={tc.tool} args={tc.args} completed />
      ))}
      {streamingContent !== null && (
        <MessageBubble
          message={{
            role: "assistant",
            content: streamingContent || streamingHint,
            created_at: new Date().toISOString(),
          }}
          streaming
        />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/chat/message-list.tsx
git commit -m "feat: add MessageList component with auto-scroll"
```

---

### Task 16: /chat 페이지 통합 (state + SSE 핸들링)

**Files:**
- Create: `frontend/src/app/chat/page.tsx`

- [ ] **Step 1: 페이지 작성**

Create `frontend/src/app/chat/page.tsx`:

```typescript
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getThreadHistory, streamChat } from "@/services/api";
import { showToast } from "@/components/ui/toast";
import { ChatSidebar } from "@/components/chat/chat-sidebar";
import { MessageList, type ToolCallInProgress } from "@/components/chat/message-list";
import { ChatInput } from "@/components/chat/chat-input";
import type { ChatMessage } from "@/types/chat";

const THREAD_KEY = "stockinsight-chat-thread";
const HINTS = [
  "질문을 이해하고 있어요...",
  "데이터를 조회중이에요...",
  "답변을 준비하고 있어요...",
];
const EXAMPLES = [
  "삼성전자 지금 어때?",
  "반도체 종목 뭐 있어?",
  "내 즐겨찾기 요약해줘",
  "오늘 주목할 뉴스?",
];

export default function ChatPage() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingHint, setStreamingHint] = useState(HINTS[0]);
  const [toolCalls, setToolCalls] = useState<ToolCallInProgress[]>([]);
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // thread 복원
  useEffect(() => {
    const saved = localStorage.getItem(THREAD_KEY);
    if (saved) setThreadId(saved);
  }, []);

  // thread 변경 시 history 로드
  useEffect(() => {
    if (!threadId) {
      setMessages([]);
      localStorage.removeItem(THREAD_KEY);
      return;
    }
    localStorage.setItem(THREAD_KEY, threadId);
    getThreadHistory(threadId)
      .then(setMessages)
      .catch(() => showToast("대화 로드 실패", "error"));
  }, [threadId]);

  // Hint 순환 (3초마다)
  useEffect(() => {
    if (!streaming) return;
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % HINTS.length;
      setStreamingHint(HINTS[i]);
    }, 3000);
    return () => clearInterval(interval);
  }, [streaming]);

  const handleSend = useCallback(
    async (message: string) => {
      const userMsg: ChatMessage = {
        role: "user",
        content: message,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);
      setStreamingContent("");
      setStreamingHint(HINTS[0]);
      setToolCalls([]);

      const abort = new AbortController();
      abortRef.current = abort;

      let accumulated = "";
      const roundToolCalls: ToolCallInProgress[] = [];

      try {
        for await (const event of streamChat(message, threadId, abort.signal)) {
          if (event.event === "token") {
            accumulated += event.data.content;
            setStreamingContent(accumulated);
          } else if (event.event === "tool_call") {
            roundToolCalls.push({
              tool: event.data.tool,
              args: event.data.args as Record<string, unknown>,
              key: Date.now() + roundToolCalls.length,
            });
            setToolCalls([...roundToolCalls]);
          } else if (event.event === "done") {
            if (!threadId) setThreadId(event.data.thread_id);
            break;
          } else if (event.event === "error") {
            showToast(event.data.error, "error");
            break;
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          showToast("응답을 중단했어요", "info");
        } else {
          showToast("전송 실패: " + (err as Error).message, "error");
        }
      } finally {
        // 스트리밍 콘텐츠를 메시지로 확정
        if (accumulated) {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: accumulated,
              created_at: new Date().toISOString(),
            },
          ]);
        }
        setStreamingContent(null);
        setStreaming(false);
        abortRef.current = null;
        setSidebarRefresh((x) => x + 1);
      }
    },
    [threadId]
  );

  const handleStop = () => {
    abortRef.current?.abort();
  };

  const handleSelectThread = (id: string | null) => {
    if (abortRef.current) abortRef.current.abort();
    setThreadId(id);
    setStreamingContent(null);
    setToolCalls([]);
  };

  const isEmpty = messages.length === 0 && !streaming;

  return (
    <div className="lg:pl-60">
      {/* Mobile: 햄버거 토글 */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed top-3 left-3 z-50 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 lg:hidden"
        aria-label="대화 목록 열기"
      >
        ☰
      </button>

      <ChatSidebar
        activeThreadId={threadId}
        onSelect={handleSelectThread}
        refreshKey={sidebarRefresh}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      {isEmpty ? (
        <div className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-2xl flex-col items-center justify-center px-6 pb-40 text-center">
          <h1 className="mb-3 text-2xl font-bold text-slate-50">안녕하세요 👋</h1>
          <p className="mb-8 text-sm text-slate-400">
            관심 있는 종목에 대해 자연어로 물어보세요.
          </p>
          <div className="grid w-full gap-2 sm:grid-cols-2">
            {EXAMPLES.map((q) => (
              <button
                key={q}
                onClick={() => handleSend(q)}
                className="rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 text-left text-sm text-slate-300 transition-colors hover:border-purple-500/30 hover:bg-purple-500/5"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <MessageList
          messages={messages}
          toolCalls={toolCalls}
          streamingContent={streamingContent}
          streamingHint={streamingHint}
        />
      )}

      <ChatInput streaming={streaming} onSend={handleSend} onStop={handleStop} />
    </div>
  );
}
```

- [ ] **Step 2: 타입 체크 + dev 서버 기동**

Run: `cd frontend && npx tsc --noEmit`

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/chat/page.tsx
git commit -m "feat: add /chat page wiring sidebar + message list + input + SSE"
```

---

### Task 17: Top-nav에 /chat 링크 추가

**Files:**
- Modify: `frontend/src/components/layout/top-nav.tsx`

- [ ] **Step 1: 링크 추가**

Modify `frontend/src/components/layout/top-nav.tsx`. "즐겨찾기" 링크 바로 앞에 Chat 링크 추가:

```typescript
<Link
  href="/chat"
  className="text-sm text-purple-400 transition-colors hover:text-purple-300"
>
  💬 챗
</Link>
<Link
  href="/"
  className="text-sm text-yellow-400 hover:text-yellow-300 transition-colors"
>
  즐겨찾기
</Link>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/top-nav.tsx
git commit -m "feat: add /chat link to top nav"
```

---

### Task 18: 수동 Smoke Test (런타임)

**Files:** 없음 (수동 검증만)

- [ ] **Step 1: 백엔드 기동**

Run (터미널 1): `cd backend && uv run uvicorn app.main:app --reload --port 8000`

Expected: `Uvicorn running on http://127.0.0.1:8000`

- [ ] **Step 2: 프론트엔드 기동**

Run (터미널 2): `cd frontend && npm run dev`

Expected: `Ready on http://localhost:3000`

- [ ] **Step 3: /chat 접속**

Browser: `http://localhost:3000/chat`

Expected: 빈 상태 (인사말 + 예시 질문 4개 칩).

- [ ] **Step 4: 예시 질문 클릭**

Click: "삼성전자 지금 어때?"

Expected:
1. 즉시 user 말풍선 표시
2. 3-5초 이내 사지적 단서 ("질문을 이해하고 있어요...")
3. tool_call 배지 표시 ("📊 005930 스냅샷 조회 중...")
4. 토큰 스트리밍 시작 (typewriter)
5. 완료 후 입력창 재활성

- [ ] **Step 5: 사이드바 확인**

Expected: 좌측에 방금 만든 thread가 preview로 표시됨.

- [ ] **Step 6: 새 대화 + 복귀 테스트**

1. [+ 새 대화] 클릭 → 빈 상태로 복귀
2. 방금 만든 thread 클릭 → 대화 복원
3. 페이지 새로고침 → localStorage의 thread_id 복원

- [ ] **Step 7: 모바일 레이아웃 확인 (DevTools)**

1. Chrome DevTools → Mobile emulator (375px)
2. 사이드바 숨김, 햄버거 ☰ 표시 확인
3. 햄버거 클릭 → drawer slide-in
4. 입력창 하단 고정 확인

- [ ] **Step 8: 중단 버튼 테스트**

1. 긴 답변을 유도하는 질문 ("반도체 종목 5개 비교해줘")
2. 스트리밍 중 ■ 중단 버튼 클릭
3. 중단 즉시 fetch abort, 토스트 "응답을 중단했어요"
4. DB 확인: partial assistant 메시지 저장됨 (thread history 복원 시 확인 가능)

- [ ] **Step 9: 버그 발견 시 대응**

- UI 깨짐: screenshot + github issue OR `/qa` skill
- API 에러: `/investigate` skill
- Commit 없음 — 검증 step임

---

### Task 19: 한국어 tool-selection eval (수동, ship gate)

**Files:**
- Create: `backend/scripts/eval_korean_queries.md` (체크리스트)

**이유:** Phase A 출시 전 agent가 한국어 질문에 올바른 tool을 선택하는지 수동 확인. 80% 이상 기대 tool 선택이 ship gate.

- [ ] **Step 1: Eval 체크리스트 작성**

Create `backend/scripts/eval_korean_queries.md`:

```markdown
# Phase A Ship Gate — Korean Tool-Selection Eval

각 질문을 /chat에서 전송 후:
1. 기대 tool이 호출됐는지 (배지 확인)
2. 응답이 DB 기반 근거를 포함하는지 (숫자/종목명/뉴스 제목)

통과 기준: 20개 중 16개 이상 (80%) 기대 동작.

## 기본 종목 조회 (기대: get_stock_snapshot)

- [ ] "삼성전자 지금 어때?"
- [ ] "테슬라 주가 알려줘"
- [ ] "SK하이닉스 PER 얼마야?"
- [ ] "005930 상세 정보"
- [ ] "애플 시가총액"

## 뉴스 조회 (기대: get_recent_news)

- [ ] "삼성전자 최근 뉴스 뭐 있어?"
- [ ] "TSLA 관련 소식 알려줘"
- [ ] "반도체 뉴스 요약해줘"  (검색 후 뉴스)
- [ ] "어제 삼전 무슨 일 있었어?"
- [ ] "3일 이내 하이닉스 기사"

## 종목 탐색 (기대: search_stocks → snapshot)

- [ ] "반도체 종목 뭐 있어?"
- [ ] "삼성이 붙은 종목 찾아줘"
- [ ] "EV 관련 미국 주식"

## 복합 질의 (기대: 2-3 tool 조합)

- [ ] "삼성전자와 SK하이닉스 PER 비교"
- [ ] "테슬라 대신 다른 EV 종목 뭐 있어?"
- [ ] "내 즐겨찾기 종목 요약"  (edge case — favorites tool 없음, 우아하게 안내)

## 일반 질문 (기대: tool 호출 없음, 자연스러운 답변)

- [ ] "안녕하세요"
- [ ] "오늘 날씨 어때?"
- [ ] "너는 누구야?"
- [ ] "투자 조언 좀"

## 결과 요약

- 통과: __ / 20
- 실패 목록:
  - [질문] → [기대 tool] → [실제 동작]
- 프롬프트 튜닝 필요 여부: ___
```

- [ ] **Step 2: 수동 실행 + 결과 기록**

체크리스트 돌면서 각 항목 ✓ or ✗ 표시.

- [ ] **Step 3: 80% 통과 시 Commit**

```bash
git add backend/scripts/eval_korean_queries.md
git commit -m "docs: add Korean tool-selection eval checklist for Phase A ship gate"
```

실패율 20% 초과 시:
1. `app/services/chat/stream.py` SYSTEM_PROMPT 수정
2. 다시 eval 돌리기 (max 3 반복)
3. 3회 넘게 개선 안 되면 STOP → `/investigate` 또는 model 변경 검토

---

### Task 20: tasks.md + TODOS.md 업데이트

**Files:**
- Modify: `docs/tasks.md`
- Modify: `TODOS.md`

- [ ] **Step 1: tasks.md의 Phase 2.5 섹션 업데이트**

Modify `docs/tasks.md`:

기존 Phase 2.5 섹션을 찾아 다음으로 교체:

```markdown
## Phase 2.5 — 대화형 Chat Agent (Phase A, 2026-04-16~)

Design: `~/.gstack/projects/feone90-stock-insight/main-design-20260416-phase-a-revised.md`
Plan: `docs/superpowers/plans/2026-04-16-phase-a-chat-agent.md`

**Scope 축소:** LangGraph/Checkpointer/AzureChatOpenAI는 Phase B로 이연. Phase A는 기존 `AzureOpenAIAdapter` 확장 + `chat_messages` 테이블 + SSE.

### Phase A (현재)
- [ ] Test DB isolation (선행 PR)
- [ ] Foundry Responses API function calling smoke test (선행)
- [ ] chat_messages 테이블 + migration
- [ ] 3 tools: get_stock_snapshot, get_recent_news, search_stocks
- [ ] AzureOpenAIAdapter.chat_with_tools 확장
- [ ] Chat API (POST SSE + GET threads/history + DELETE)
- [ ] /chat 페이지 + 사이드바 + 입력창 + 말풍선
- [ ] 한국어 eval 20문항 (ship gate 80%)

### Phase B (Phase A 검증 후)
- [ ] LangGraph + AsyncPostgresSaver 도입
- [ ] Research agent (외부 뉴스 + 교차 검증)
- [ ] Analysis agent (감성/재무 교차)
- [ ] Supervisor (LLM 라우터)
```

- [ ] **Step 2: Commit**

```bash
git add docs/tasks.md
git commit -m "docs: update tasks.md with Phase 2.5 Phase A scope"
```

---

## Self-Review Checklist

이 plan을 실행자가 blind로 받았을 때 막힐 곳 체크:

1. **Spec coverage** — 모든 design doc 결정이 태스크로 매핑됐나?
   - ✅ 좌측 사이드바 → Task 14
   - ✅ 말풍선 스타일 → Task 11
   - ✅ tool_call 배지 → Task 12
   - ✅ 전송/중단 토글 → Task 13
   - ✅ 빈 상태 예시 질문 → Task 16
   - ✅ 사지적 단서 메시지 → Task 16 (HINTS)
   - ✅ 마크다운 → Task 9, 11
   - ✅ 모바일 햄버거 → Task 14, 16
   - ✅ Toast + undo 삭제 → Task 14
   - ✅ hover 타임스탬프/복사 → Task 11
   - ✅ a11y aria-live → Task 12, 15

2. **Placeholder scan** — "TBD", "TODO", "implement later" 없음. 모든 step에 실제 코드.

3. **Type consistency** — `ChatMessage` 타입, `SseEvent` 유니온, `thread_id` UUID 타입, `ChatRole` 리터럴 — 전부 일관.

4. **Test order** — 각 task에서 TDD: test 먼저 → fail 확인 → 구현 → pass 확인 → commit.

5. **Dependency 순서** — Task 3(tools) → Task 6(adapter uses tools) → Task 7(stream uses both) → Task 8(API uses stream) → Task 10+(frontend). OK.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-16-phase-a-chat-agent.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — 나(메인 agent)가 task별로 fresh subagent를 dispatch, task 간 리뷰 체크포인트. 빠른 이터레이션, 맥락 오염 방지.

2. **Inline Execution** — 이 세션에서 직접 task를 순서대로 실행. 배치 실행 + 체크포인트로 중간 리뷰.

**Which approach?**
