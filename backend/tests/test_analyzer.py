"""Analyzer 파이프라인 테스트."""

import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm.analyzer import analyze_stock, _parse_llm_response, ANALYSIS_PERIOD_TYPE


SAMPLE_LLM_RESPONSE = json.dumps({
    "keywords": [
        {
            "keyword": "HBM 수주 확대",
            "type": "bullish",
            "detail": "SK하이닉스 HBM3E 수주 확대 소식",
            "source": "네이버뉴스",
            "impact_level": "high",
            "duration": "mid",
        },
        {
            "keyword": "환율 상승",
            "type": "bearish",
            "detail": "원달러 환율 상승 부담",
            "source": "네이버뉴스",
            "impact_level": "mid",
            "duration": "short",
        },
    ],
    "daily_keywords": [
        {"date": "2026-04-12", "keyword": "HBM 수주", "type": "bullish"},
        {"date": "2026-04-11", "keyword": "환율 상승", "type": "bearish"},
    ],
    "summary": "이번 주 삼성전자는 HBM 수주 확대 소식에 상승했습니다.",
    "feedback": "중장기적으로 HBM 사업 확대에 주목하세요.",
})


# --- _parse_llm_response tests ---


class TestParseLlmResponse:
    def test_valid_json(self):
        data = _parse_llm_response(SAMPLE_LLM_RESPONSE)
        assert len(data["keywords"]) == 2
        assert data["keywords"][0]["keyword"] == "HBM 수주 확대"
        assert data["keywords"][0]["type"] == "bullish"
        assert len(data["daily_keywords"]) == 2
        assert data["summary"] != ""
        assert data["feedback"] != ""

    def test_markdown_fence(self):
        wrapped = f"```json\n{SAMPLE_LLM_RESPONSE}\n```"
        data = _parse_llm_response(wrapped)
        assert len(data["keywords"]) == 2

    def test_missing_fields(self):
        data = _parse_llm_response('{"keywords": []}')
        assert data["keywords"] == []
        assert data["daily_keywords"] == []
        assert data["summary"] == ""
        assert data["feedback"] == ""

    def test_invalid_type_normalized(self):
        raw = json.dumps({
            "keywords": [{"keyword": "test", "type": "INVALID", "impact_level": "xxx", "duration": "yyy"}],
        })
        data = _parse_llm_response(raw)
        assert data["keywords"][0]["type"] == "neutral"
        assert data["keywords"][0]["impact_level"] == "mid"
        assert data["keywords"][0]["duration"] == "mid"

    def test_invalid_daily_type_normalized(self):
        raw = json.dumps({
            "daily_keywords": [{"date": "2026-04-12", "keyword": "test", "type": "wrong"}],
        })
        data = _parse_llm_response(raw)
        assert data["daily_keywords"][0]["type"] == "neutral"

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_response("not json at all")

    def test_empty_object(self):
        data = _parse_llm_response("{}")
        assert data["keywords"] == []
        assert data["summary"] == ""


# --- analyze_stock tests ---


def _make_stock(ticker="005930", name="삼성전자", market="KRX"):
    stock = MagicMock()
    stock.id = 1
    stock.ticker = ticker
    stock.name = name
    stock.market = market
    stock.current_price = 71500
    stock.change_percent = -1.65
    return stock


def _make_news(title="테스트 뉴스", days_ago=0):
    n = MagicMock()
    n.title = title
    n.published_at = datetime.now() - timedelta(days=days_ago)
    n.source = "네이버뉴스"
    n.stock_id = 1
    return n


def _make_disclosure(title="테스트 공시", days_ago=0):
    d = MagicMock()
    d.title = title
    d.disclosed_at = datetime.now() - timedelta(days=days_ago)
    d.disclosure_type = "정기공시"
    d.stock_id = 1
    return d


class TestAnalyzeStock:
    @pytest.mark.asyncio
    async def test_success(self):
        stock = _make_stock()
        adapter = AsyncMock()
        adapter.generate_json = AsyncMock(return_value=SAMPLE_LLM_RESPONSE)

        db = AsyncMock()
        # news query
        news_result = MagicMock()
        news_result.scalars.return_value.all.return_value = [_make_news()]
        # disclosure query
        disc_result = MagicMock()
        disc_result.scalars.return_value.all.return_value = [_make_disclosure()]
        # existing analysis query (empty)
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[news_result, disc_result, existing_result])

        result = await analyze_stock(db, stock, adapter)

        assert result["analysis_created"] is True
        adapter.generate_json.assert_called_once()
        db.add.assert_called()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_news_no_disclosures(self):
        stock = _make_stock()
        adapter = AsyncMock()
        db = AsyncMock()

        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[empty, empty])

        result = await analyze_stock(db, stock, adapter)

        assert result["analysis_created"] is False
        assert "뉴스/공시 없음" in result["error"]
        adapter.generate_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_json_parse_failure(self):
        stock = _make_stock()
        adapter = AsyncMock()
        adapter.generate_json = AsyncMock(return_value="not valid json")

        db = AsyncMock()
        news_result = MagicMock()
        news_result.scalars.return_value.all.return_value = [_make_news()]
        disc_result = MagicMock()
        disc_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[news_result, disc_result])

        result = await analyze_stock(db, stock, adapter)

        assert result["analysis_created"] is False
        assert "JSON 파싱 실패" in result["error"]

    @pytest.mark.asyncio
    async def test_llm_exception(self):
        stock = _make_stock()
        adapter = AsyncMock()
        adapter.generate_json = AsyncMock(side_effect=Exception("API timeout"))

        db = AsyncMock()
        news_result = MagicMock()
        news_result.scalars.return_value.all.return_value = [_make_news()]
        disc_result = MagicMock()
        disc_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[news_result, disc_result])

        result = await analyze_stock(db, stock, adapter)

        assert result["analysis_created"] is False
        assert "분석 실패" in result["error"]

    @pytest.mark.asyncio
    async def test_replaces_existing_analysis(self):
        stock = _make_stock()
        adapter = AsyncMock()
        adapter.generate_json = AsyncMock(return_value=SAMPLE_LLM_RESPONSE)

        old_analysis = MagicMock()
        db = AsyncMock()
        news_result = MagicMock()
        news_result.scalars.return_value.all.return_value = [_make_news()]
        disc_result = MagicMock()
        disc_result.scalars.return_value.all.return_value = []
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = [old_analysis]

        db.execute = AsyncMock(side_effect=[news_result, disc_result, existing_result])

        result = await analyze_stock(db, stock, adapter)

        assert result["analysis_created"] is True
        db.delete.assert_called_once_with(old_analysis)
