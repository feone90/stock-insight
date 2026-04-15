# News Article Content Scraping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape full article content from news URLs and include it in LLM analysis prompts, replacing the current title-only approach for dramatically improved stock analysis quality.

**Architecture:** Add a `content` column to the News table, introduce a `scraper.py` module using `trafilatura` for article text extraction, integrate scraping into the existing `sync_news()` pipeline (so no changes needed in admin.py or scheduler.py), and update the LLM prompt to include article body text (truncated to ~1000 chars per article, 20 articles max = ~5,000 tokens, well within GPT-4o's 128K context).

**Tech Stack:** trafilatura (article extraction), httpx (async HTTP, already in project), SQLAlchemy (ORM), Alembic (migration)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/models/news.py` | Add `content` column (Text, nullable) |
| Create | `backend/alembic/versions/*_add_content_to_news.py` | Migration via alembic autogenerate |
| Create | `backend/app/collectors/scraper.py` | Article content fetching + extraction |
| Modify | `backend/app/collectors/news.py` | Save API descriptions, call scraper after collection |
| Modify | `backend/app/services/llm/analyzer.py` | Pass `content` field to prompt builder |
| Modify | `backend/app/services/llm/prompts.py` | Include article body in prompt, update guidelines |
| Create | `backend/tests/test_scraper.py` | Scraper unit tests |
| Modify | `backend/tests/test_us_news.py` | Update routing tests + add scraper integration tests |
| Modify | `backend/tests/test_analyzer.py` | Verify content flows to prompt |
| Modify | `backend/pyproject.toml` | Add `trafilatura` dependency |

---

### Task 1: News model + migration

**Files:**
- Modify: `backend/app/models/news.py`
- Create: `backend/alembic/versions/*_add_content_to_news.py` (via alembic)

- [ ] **Step 1: Add content column to News model**

In `backend/app/models/news.py`, add `Text` import and `content` column:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class News(Base):
    __tablename__ = "news"
    __table_args__ = (UniqueConstraint("stock_id", "url", name="uq_news_stock_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    title: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(1000))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 2: Generate and apply migration**

Run: `cd backend && uv run alembic revision --autogenerate -m "add content to news"`
Then: `cd backend && uv run alembic upgrade head`

Expected: Migration created and applied. Verify with `uv run alembic current`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/news.py backend/alembic/versions/*add_content*
git commit -m "feat: add content column to news table for article body storage"
```

---

### Task 2: Create scraper module (TDD)

**Files:**
- Create: `backend/tests/test_scraper.py`
- Create: `backend/app/collectors/scraper.py`
- Modify: `backend/pyproject.toml` (add trafilatura)

- [ ] **Step 1: Write scraper tests**

```python
# backend/tests/test_scraper.py
"""Article content scraper tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.collectors.scraper import fetch_article_content, scrape_news_content


class TestFetchArticleContent:
    @pytest.mark.asyncio
    @patch("app.collectors.scraper._extract_text", return_value="Full article content about market trends and earnings.")
    @patch("app.collectors.scraper._fetch_html", new_callable=AsyncMock, return_value="<html><body>Article</body></html>")
    async def test_success(self, mock_fetch, mock_extract):
        result = await fetch_article_content("https://example.com/article")
        assert result == "Full article content about market trends and earnings."
        mock_fetch.assert_called_once_with("https://example.com/article")
        mock_extract.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.collectors.scraper._fetch_html", new_callable=AsyncMock, return_value=None)
    async def test_fetch_returns_none(self, mock_fetch):
        result = await fetch_article_content("https://example.com/404")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.collectors.scraper._extract_text", return_value=None)
    @patch("app.collectors.scraper._fetch_html", new_callable=AsyncMock, return_value="<html></html>")
    async def test_extraction_returns_none(self, mock_fetch, mock_extract):
        result = await fetch_article_content("https://example.com/empty")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.collectors.scraper._extract_text", return_value="x" * 10000)
    @patch("app.collectors.scraper._fetch_html", new_callable=AsyncMock, return_value="<html>Long</html>")
    async def test_content_truncated_to_max_length(self, mock_fetch, mock_extract):
        result = await fetch_article_content("https://example.com/long")
        assert len(result) == 5000


class TestScrapeNewsContent:
    @pytest.mark.asyncio
    @patch("app.collectors.scraper.fetch_article_content", new_callable=AsyncMock, return_value="Scraped full article content")
    async def test_scrapes_null_content_articles(self, mock_fetch):
        article = MagicMock()
        article.url = "https://example.com/news1"
        article.content = None

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [article]
        db.execute = AsyncMock(return_value=result_mock)

        result = await scrape_news_content(db, stock_id=1)

        assert result["scraped"] == 1
        assert article.content == "Scraped full article content"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_articles_to_scrape(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await scrape_news_content(db, stock_id=1)

        assert result["scraped"] == 0
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.collectors.scraper.fetch_article_content", new_callable=AsyncMock, return_value="Content")
    async def test_skips_articles_without_url(self, mock_fetch):
        article_no_url = MagicMock()
        article_no_url.url = ""
        article_no_url.content = None

        article_with_url = MagicMock()
        article_with_url.url = "https://example.com/news"
        article_with_url.content = None

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [article_no_url, article_with_url]
        db.execute = AsyncMock(return_value=result_mock)

        result = await scrape_news_content(db, stock_id=1)

        assert result["scraped"] == 1
        mock_fetch.assert_called_once_with("https://example.com/news")

    @pytest.mark.asyncio
    @patch("app.collectors.scraper.fetch_article_content", new_callable=AsyncMock, return_value="Short")
    async def test_keeps_longer_existing_content(self, mock_fetch):
        article = MagicMock()
        article.url = "https://example.com/news"
        article.content = "This is already a longer existing content from the API description field"

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [article]
        db.execute = AsyncMock(return_value=result_mock)

        result = await scrape_news_content(db, stock_id=1)

        assert result["scraped"] == 0
        assert article.content == "This is already a longer existing content from the API description field"

    @pytest.mark.asyncio
    @patch("app.collectors.scraper.fetch_article_content", new_callable=AsyncMock, return_value=None)
    async def test_scrape_failure_leaves_content_unchanged(self, mock_fetch):
        article = MagicMock()
        article.url = "https://example.com/paywalled"
        article.content = None

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [article]
        db.execute = AsyncMock(return_value=result_mock)

        result = await scrape_news_content(db, stock_id=1)

        assert result["scraped"] == 0
        assert article.content is None
        db.commit.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_scraper.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.collectors.scraper'`

- [ ] **Step 3: Add trafilatura dependency**

Run: `cd backend && uv add trafilatura`

- [ ] **Step 4: Implement scraper module**

```python
# backend/app/collectors/scraper.py
"""뉴스 기사 본문 스크래핑."""

import asyncio
import logging

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News

logger = logging.getLogger(__name__)

SCRAPE_TIMEOUT = 10
MAX_CONTENT_LENGTH = 5000
SCRAPE_CONCURRENCY = 5
MIN_CONTENT_LENGTH = 200

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


async def _fetch_html(url: str) -> str | None:  # pragma: no cover
    """URL에서 HTML을 가져온다."""
    try:
        async with httpx.AsyncClient(
            timeout=SCRAPE_TIMEOUT, follow_redirects=True, headers=HEADERS
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            return resp.text
    except Exception:
        return None


def _extract_text(html: str) -> str | None:  # pragma: no cover
    """trafilatura로 HTML에서 기사 본문을 추출한다."""
    import trafilatura

    return trafilatura.extract(html, include_comments=False, include_tables=False)


async def fetch_article_content(url: str) -> str | None:
    """URL에서 기사 본문을 스크래핑한다."""
    html = await _fetch_html(url)
    if not html:
        return None

    text = await asyncio.to_thread(_extract_text, html)
    if text:
        return text[:MAX_CONTENT_LENGTH]
    return None


async def scrape_news_content(
    db: AsyncSession,
    stock_id: int,
    limit: int = 20,
) -> dict:
    """본문이 없거나 짧은 기사의 content를 스크래핑으로 채운다.

    Returns:
        {"scraped": N} — 실제로 content가 업데이트된 기사 수
    """
    result = await db.execute(
        select(News)
        .where(
            News.stock_id == stock_id,
            (News.content.is_(None))
            | (func.length(News.content) < MIN_CONTENT_LENGTH),
        )
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    articles = result.scalars().all()

    if not articles:
        return {"scraped": 0}

    sem = asyncio.Semaphore(SCRAPE_CONCURRENCY)

    async def _scrape_one(article: News) -> bool:
        async with sem:
            content = await fetch_article_content(article.url)
            if content and len(content) > len(article.content or ""):
                article.content = content
                return True
            return False

    tasks = [_scrape_one(a) for a in articles if a.url]
    results = await asyncio.gather(*tasks)

    count = sum(1 for r in results if r)
    if count > 0:
        await db.commit()

    return {"scraped": count}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_scraper.py -v`

Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/collectors/scraper.py backend/tests/test_scraper.py backend/pyproject.toml backend/uv.lock
git commit -m "feat: add article content scraper using trafilatura"
```

---

### Task 3: Update news collectors to save API descriptions + integrate scraper

**Files:**
- Modify: `backend/app/collectors/news.py`
- Modify: `backend/tests/test_us_news.py`

- [ ] **Step 1: Add scraper integration tests**

Append to `backend/tests/test_us_news.py`:

```python
# --- add these imports at the top ---
from app.collectors.news import _sync_newsapi

# --- add at the bottom of the file ---

class TestSyncNewsWithScraping:
    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, return_value={"scraped": 3})
    @patch("app.collectors.news._sync_newsapi", new_callable=AsyncMock, return_value={"news_synced": 10})
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock, return_value={"news_synced": 5})
    async def test_us_sync_calls_scraper(self, mock_yf, mock_newsapi, mock_scrape):
        db = AsyncMock()
        stock = _make_stock("TSLA", "NASDAQ")
        result = await sync_news(db, stock)

        mock_scrape.assert_called_once_with(db, stock.id)
        assert result["news_synced"] == 15
        assert result["scraped"] == 3

    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, return_value={"scraped": 5})
    @patch("app.collectors.news._sync_naver_news", new_callable=AsyncMock, return_value={"news_synced": 20})
    async def test_kr_sync_calls_scraper(self, mock_naver, mock_scrape):
        db = AsyncMock()
        stock = _make_stock("005930", "KRX")
        result = await sync_news(db, stock)

        mock_scrape.assert_called_once_with(db, stock.id)
        assert result["news_synced"] == 20
        assert result["scraped"] == 5

    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, side_effect=Exception("scrape error"))
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock, return_value={"news_synced": 5})
    @patch("app.collectors.news._sync_newsapi", new_callable=AsyncMock, return_value={"news_synced": 0})
    async def test_scraper_failure_does_not_break_sync(self, mock_newsapi, mock_yf, mock_scrape):
        db = AsyncMock()
        stock = _make_stock("TSLA", "NASDAQ")
        result = await sync_news(db, stock)

        assert result["news_synced"] == 5
        assert result["scraped"] == 0  # graceful fallback


class TestNewsApiSavesDescription:
    @pytest.mark.asyncio
    @patch("app.collectors.news.fetch_newsapi", new_callable=AsyncMock)
    async def test_description_saved_as_content(self, mock_fetch):
        mock_fetch.return_value = {
            "articles": [
                {
                    "title": "Tesla earnings beat",
                    "url": "https://example.com/tesla",
                    "source": {"name": "Reuters"},
                    "publishedAt": "2026-04-14T10:00:00Z",
                    "description": "Tesla reported strong Q1 results with revenue exceeding expectations.",
                },
            ]
        }

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute = AsyncMock(return_value=result_mock)

        result = await _sync_newsapi(db, _make_stock())
        assert result["news_synced"] == 1

        # Verify the insert included content
        call_args = db.execute.call_args_list[0]
        stmt = call_args[0][0]
        # The insert statement's compile params should contain content
        compiled = stmt.compile()
        assert "content" in str(compiled)
```

Also update the existing `TestSyncNewsRouting` to mock scraper:

```python
class TestSyncNewsRouting:
    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, return_value={"scraped": 0})
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock, return_value={"news_synced": 5})
    @patch("app.collectors.news._sync_naver_news", new_callable=AsyncMock)
    async def test_us_stock_uses_yfinance(self, mock_naver, mock_yf, mock_scrape):
        db = AsyncMock()
        result = await sync_news(db, _make_stock("TSLA", "NASDAQ"))
        mock_yf.assert_called_once()
        mock_naver.assert_not_called()
        assert result["news_synced"] == 5

    @pytest.mark.asyncio
    @patch("app.collectors.news.scrape_news_content", new_callable=AsyncMock, return_value={"scraped": 0})
    @patch("app.collectors.news._sync_yfinance_news", new_callable=AsyncMock)
    @patch("app.collectors.news._sync_naver_news", new_callable=AsyncMock, return_value={"news_synced": 10})
    async def test_kr_stock_uses_naver(self, mock_naver, mock_yf, mock_scrape):
        db = AsyncMock()
        result = await sync_news(db, _make_stock("005930", "KRX"))
        mock_naver.assert_called_once()
        mock_yf.assert_not_called()
        assert result["news_synced"] == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_us_news.py -v`

Expected: FAIL — `scrape_news_content` not imported in news.py, content not in insert

- [ ] **Step 3: Update news.py — Naver collector saves description**

In `backend/app/collectors/news.py`, in `_sync_naver_news`, change the insert to include content:

```python
        content = strip_html(item.get("description", "")) or None

        stmt = insert(News).values(
            stock_id=stock.id,
            title=strip_html(item.get("title", "")),
            source="네이버뉴스",
            url=item.get("link", ""),
            published_at=pub_date,
            content=content,
        ).on_conflict_do_nothing(constraint="uq_news_stock_url")
```

- [ ] **Step 4: Update news.py — NewsAPI collector saves description**

In `_sync_newsapi`, add content extraction:

```python
        content = article.get("description") or article.get("content") or None

        stmt = insert(News).values(
            stock_id=stock.id,
            title=title[:500],
            source=source_name,
            url=url[:1000],
            published_at=pub_date,
            content=content,
        ).on_conflict_do_nothing(constraint="uq_news_stock_url")
```

- [ ] **Step 5: Update news.py — integrate scraper into sync_news**

Add import at top and update `sync_news`:

```python
from app.collectors.scraper import scrape_news_content

async def sync_news(db: AsyncSession, stock: Stock) -> dict:
    """종목 시장에 따라 적절한 뉴스 소스로 동기화한다."""
    if stock.market in ("NYSE", "NASDAQ"):
        yf_result = await _sync_yfinance_news(db, stock)
        api_result = await _sync_newsapi(db, stock)
        total = yf_result.get("news_synced", 0) + api_result.get("news_synced", 0)
        errors = []
        for r in [yf_result, api_result]:
            if "error" in r:
                errors.append(r["error"])
        result = {"news_synced": total}
        if errors:
            result["error"] = "; ".join(errors)
    else:
        result = await _sync_naver_news(db, stock)

    # 본문 스크래핑 (실패해도 뉴스 수집 결과는 유지)
    try:
        scrape_result = await scrape_news_content(db, stock.id)
        result["scraped"] = scrape_result.get("scraped", 0)
    except Exception as e:
        logger.warning("Content scraping failed for %s: %s", stock.ticker, e)
        result["scraped"] = 0

    return result
```

Also add `logger` at top of `news.py` if not already present:

```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 6: Run tests**

Run: `cd backend && uv run python -m pytest tests/test_us_news.py -v`

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/collectors/news.py backend/tests/test_us_news.py
git commit -m "feat: integrate article scraping into news sync pipeline"
```

---

### Task 4: Update LLM analyzer and prompt (TDD)

**Files:**
- Modify: `backend/tests/test_analyzer.py`
- Modify: `backend/app/services/llm/analyzer.py`
- Modify: `backend/app/services/llm/prompts.py`

- [ ] **Step 1: Update test helper and add content test**

In `backend/tests/test_analyzer.py`, update `_make_news` and add a test:

```python
def _make_news(title="테스트 뉴스", days_ago=0, content=None):
    n = MagicMock()
    n.title = title
    n.published_at = datetime.now() - timedelta(days=days_ago)
    n.source = "네이버뉴스"
    n.url = "https://example.com/news"
    n.content = content
    n.stock_id = 1
    return n
```

Add inside `TestAnalyzeStock`:

```python
    @pytest.mark.asyncio
    async def test_content_included_in_prompt(self):
        stock = _make_stock()
        adapter = AsyncMock()
        adapter.generate_json = AsyncMock(return_value=SAMPLE_LLM_RESPONSE)

        news_with_content = _make_news(
            title="HBM 수주 확대",
            content="SK하이닉스가 엔비디아로부터 HBM3E 대규모 수주를 확보했다. 수주 금액은 약 2조원 규모로 추정된다.",
        )

        db = AsyncMock()
        news_result = MagicMock()
        news_result.scalars.return_value.all.return_value = [news_with_content]
        disc_result = MagicMock()
        disc_result.scalars.return_value.all.return_value = []
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[news_result, disc_result, existing_result])

        await analyze_stock(db, stock, adapter)

        prompt = adapter.generate_json.call_args[0][0]
        assert "HBM3E 대규모 수주" in prompt
        assert "2조원" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_analyzer.py::TestAnalyzeStock::test_content_included_in_prompt -v`

Expected: FAIL — content not passed to prompt

- [ ] **Step 3: Update analyzer to pass content**

In `backend/app/services/llm/analyzer.py`, update the news_list construction (around line 52-60):

```python
        news_list = [
            {
                "title": n.title,
                "published_at": n.published_at.strftime("%Y-%m-%d") if n.published_at else "",
                "source": n.source or "",
                "url": n.url or "",
                "content": n.content or "",
            }
            for n in news_rows
        ]
```

- [ ] **Step 4: Update prompt builder**

Replace the `build_analysis_prompt` function and add helper in `backend/app/services/llm/prompts.py`:

```python
MAX_NEWS_ITEMS = 20
MAX_CONTENT_PER_ARTICLE = 1000


def _format_news_item(n: dict) -> str:
    """뉴스 항목을 프롬프트 텍스트로 포맷한다."""
    date = n.get("published_at", "")
    title = n.get("title", "")
    source = n.get("source", "")
    url = n.get("url", "")
    content = n.get("content", "")

    header = f"### [{date}] {title}"
    meta = f"출처: {source} | URL: {url}"

    if content:
        truncated = content[:MAX_CONTENT_PER_ARTICLE]
        if len(content) > MAX_CONTENT_PER_ARTICLE:
            truncated += "..."
        return f"{header}\n{meta}\n{truncated}"
    else:
        return f"{header}\n{meta}\n(본문 없음)"


def build_analysis_prompt(
    stock_name: str,
    ticker: str,
    market: str,
    current_price: float | None,
    change_percent: float | None,
    news_list: list[dict],
    disclosure_list: list[dict],
) -> str:
    """뉴스/공시 데이터로 분석 프롬프트를 생성한다."""
    truncated_news = news_list[:MAX_NEWS_ITEMS]
    news_text = "\n\n".join(_format_news_item(n) for n in truncated_news)
    if not news_text:
        news_text = "(뉴스 없음)"

    disc_text = "\n".join(
        f"- [{d.get('disclosed_at', '')}] {d.get('title', '')} ({d.get('disclosure_type', '')})"
        for d in disclosure_list
    )
    if not disc_text:
        disc_text = "(공시 없음)"

    price_info = ""
    if current_price is not None:
        price_info = f"- 최근 주가: {current_price:,.0f}"
        if change_percent is not None:
            price_info += f" ({change_percent:+.2f}%)"

    return f"""당신은 증권사 리서치센터의 시니어 애널리스트입니다.
개인 투자자의 실제 매매 판단에 직접 사용될 분석을 작성합니다.
뻔한 일반론이 아닌, 이 종목에 특화된 구체적이고 날카로운 인사이트를 제공하세요.

## 종목 정보
- 종목: {stock_name} ({ticker})
- 시장: {market}
{price_info}

## 최근 뉴스 ({len(truncated_news)}건)
{news_text}

## 최근 공시 ({len(disclosure_list)}건)
{disc_text}

## 분석 지침

뉴스 본문이 제공된 경우, 본문의 구체적 수치와 맥락을 반드시 활용하세요.
본문이 없는 뉴스는 제목만으로 판단하되, 확실하지 않은 내용은 추론하지 마세요.

### keywords — 최소 8개, 최대 15개
상승/하락/보합 각 카테고리에서 최소 2개 이상 추출하세요.
같은 뉴스라도 다른 각도에서 여러 키워드를 뽑을 수 있습니다.

각 키워드에 대해:
- **keyword**: 투자자가 3초 만에 이해하는 4-8글자 (예: "HBM3E 양산 본격화", "美 관세 리스크", "배당금 상향")
- **detail**: 이 요인이 주가에 미치는 구체적 영향을 분석하세요.
  - 반드시 수치를 포함 (매출 전망, 시장 점유율, 목표가 등)
  - 경쟁사 대비 비교 (삼성 vs SK하이닉스, 테슬라 vs BYD 등)
  - 시간축 명시 (단기 1-2주 vs 중기 1-3개월 vs 장기 효과)
  - 3-5문장으로 작성
- **source**: 근거가 된 뉴스의 URL을 그대로 넣으세요. URL 없으면 기사 제목.
- **impact_level**: high(주가 5%+ 영향), mid(1-5%), low(1% 미만)
- **duration**: short(1주 이내), mid(1-3개월), long(3개월+)

### daily_keywords — 뉴스가 있는 각 날짜마다 1-2개
뉴스 발행일 기준으로 각 날짜의 핵심 이벤트를 매핑하세요.

### summary — 4-5문장
- 이번 기간 주가 흐름의 핵심 드라이버
- 가장 중요한 이벤트 2-3개를 구체적으로 언급
- 시장 대비 상대적 강약 판단

### feedback — 4-5문장, 실전 투자 전략
- 매수/매도/관망 중 하나를 명확히 권고하고 이유 제시
- 적정 매수 구간 또는 손절 기준을 수치로 제시
- 향후 1-3개월 내 주의할 이벤트 (실적 발표, 배당, 정책 등)
- 포트폴리오 내 비중 조절 가이드

## 출력 규칙
- type: "bullish", "bearish", "neutral" 중 하나만
- impact_level: "high", "mid", "low" 중 하나만
- duration: "short", "mid", "long" 중 하나만
- 반드시 JSON만 출력. 다른 텍스트 없이.

{ANALYSIS_JSON_SCHEMA}"""
```

- [ ] **Step 5: Run all analyzer tests**

Run: `cd backend && uv run python -m pytest tests/test_analyzer.py -v`

Expected: All tests PASS (including the new `test_content_included_in_prompt`)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/llm/analyzer.py backend/app/services/llm/prompts.py backend/tests/test_analyzer.py
git commit -m "feat: include article content in LLM analysis prompt"
```

---

### Task 5: Full test suite + final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `cd backend && uv run python -m pytest tests/ -v --cov=app`

Expected: All tests pass, coverage >= 95%

- [ ] **Step 2: Fix any failures**

If tests fail, investigate and fix. Common issues:
- Old tests may need `content` field added to mock News objects
- Import paths may need updating

- [ ] **Step 3: Verify with a real sync (manual)**

If the backend server is running:
1. Open `http://localhost:8000/docs`
2. POST `/api/admin/sync/stock/AAPL`
3. Check response — `scraped` count should appear
4. GET `/api/stocks/AAPL/news` — articles should be returned (content is internal, not exposed in API)
5. POST another sync — the LLM analysis should now reference article body details

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "chore: fix test suite after news content scraping integration"
```
