"""Article content scraper tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.collectors.scraper import (
    _extract_script_redirect_url,
    _extract_text,
    fetch_article_content,
    scrape_news_content,
)


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

    def test_extracts_naver_finance_script_redirect(self):
        html = "<SCRIPT>top.location.href='https://n.news.naver.com/mnews/article/277/0005765419';</SCRIPT>"
        result = _extract_script_redirect_url(
            html,
            "https://finance.naver.com/item/news_read.naver?article_id=0005765419",
        )
        assert result == "https://n.news.naver.com/mnews/article/277/0005765419"

    @pytest.mark.asyncio
    @patch("app.collectors.scraper._extract_text", return_value="Redirected article body")
    @patch(
        "app.collectors.scraper._fetch_html",
        new_callable=AsyncMock,
        side_effect=[
            "<SCRIPT>top.location.href='https://n.news.naver.com/mnews/article/277/0005765419';</SCRIPT>",
            "<html><body>Redirected</body></html>",
        ],
    )
    async def test_follows_script_redirect_before_extraction(self, mock_fetch, mock_extract):
        result = await fetch_article_content("https://finance.naver.com/item/news_read.naver")

        assert result == "Redirected article body"
        assert mock_fetch.await_count == 2
        mock_extract.assert_called_once_with(
            "<html><body>Redirected</body></html>",
            "https://n.news.naver.com/mnews/article/277/0005765419",
        )

    def test_extracts_naver_article_selector(self):
        html = """
        <html><body>
          <div id="dic_area">
            SK하이닉스는 800점 만점에 최고점인 648.3점을 받아 종합 1위에 올랐다.
            CEO스코어는 고속성장, 투자, 글로벌 경쟁력 등 8개 부문을 분석했다.
            SK하이닉스는 고속성장과 투자 부문에서 높은 평가를 받았다.
          </div>
        </body></html>
        """
        result = _extract_text(html, "https://n.news.naver.com/mnews/article/277/0005765419")
        assert result is not None
        assert "648.3점" in result

    def test_extracts_yahoo_article_selector(self):
        html = """
        <html><body>
          <div data-testid="article-body">
            <p>Microsoft shares rose after the company reported stronger Azure demand.</p>
            <p>Analysts said enterprise AI spending remained resilient across large customers.</p>
            <p>The move matters because cloud revenue is a key driver for Microsoft margins.</p>
          </div>
        </body></html>
        """
        result = _extract_text(
            html,
            "https://finance.yahoo.com/markets/stocks/articles/msft-up.html",
        )
        assert result is not None
        assert "Azure demand" in result

    def test_extracts_jsonld_article_body(self):
        html = """
        <html><head>
          <script type="application/ld+json">
            {"@type":"NewsArticle","articleBody":"Microsoft expanded its AI infrastructure investments as Azure demand continued. The article says cloud capacity remains a bottleneck for enterprise customers. This body is long enough for card analysis."}
          </script>
        </head></html>
        """
        result = _extract_text(html, "https://example.com/news")
        assert result is not None
        assert "AI infrastructure" in result


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
