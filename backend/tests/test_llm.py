"""LLM adapter + prompt 테스트."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm.adapter import AzureOpenAIAdapter, OpenAIAdapter, get_adapter
from app.services.llm.prompts import build_analysis_prompt, MAX_NEWS_ITEMS


# --- Adapter tests ---


def _mock_completion(content: str):
    """OpenAI completion 응답 mock 생성."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestAzureOpenAIAdapter:
    @pytest.mark.asyncio
    async def test_generate(self):
        adapter = AzureOpenAIAdapter.__new__(AzureOpenAIAdapter)
        adapter.deployment = "gpt-4o-mini"
        adapter.client = AsyncMock()
        adapter.client.chat.completions.create.return_value = _mock_completion("hello")

        result = await adapter.generate("test prompt")

        assert result == "hello"
        adapter.client.chat.completions.create.assert_called_once()
        call_kwargs = adapter.client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["messages"] == [{"role": "user", "content": "test prompt"}]

    @pytest.mark.asyncio
    async def test_generate_json(self):
        json_resp = '{"keywords": []}'
        adapter = AzureOpenAIAdapter.__new__(AzureOpenAIAdapter)
        adapter.deployment = "gpt-4o-mini"
        adapter.client = AsyncMock()
        adapter.client.chat.completions.create.return_value = _mock_completion(json_resp)

        result = await adapter.generate_json("test prompt")

        assert result == json_resp
        call_kwargs = adapter.client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_generate_empty_content(self):
        adapter = AzureOpenAIAdapter.__new__(AzureOpenAIAdapter)
        adapter.deployment = "test"
        adapter.client = AsyncMock()
        choice = MagicMock()
        choice.message.content = None
        resp = MagicMock()
        resp.choices = [choice]
        adapter.client.chat.completions.create.return_value = resp

        result = await adapter.generate("test")
        assert result == ""


class TestOpenAIAdapter:
    @pytest.mark.asyncio
    async def test_generate(self):
        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        adapter.model = "gpt-4o-mini"
        adapter.client = AsyncMock()
        adapter.client.chat.completions.create.return_value = _mock_completion("hi")

        result = await adapter.generate("test")
        assert result == "hi"

    @pytest.mark.asyncio
    async def test_generate_json(self):
        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        adapter.model = "gpt-4o-mini"
        adapter.client = AsyncMock()
        adapter.client.chat.completions.create.return_value = _mock_completion("{}")

        result = await adapter.generate_json("test")
        assert result == "{}"
        call_kwargs = adapter.client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}


class TestGetAdapter:
    def test_azure_openai(self):
        with patch("app.services.llm.adapter.settings") as mock_settings:
            mock_settings.llm_provider = "azure_openai"
            mock_settings.llm_endpoint = "https://test.openai.azure.com"
            mock_settings.llm_api_key = "test-key"
            mock_settings.llm_deployment = "gpt-4o-mini"
            adapter = get_adapter()
            assert isinstance(adapter, AzureOpenAIAdapter)

    def test_openai(self):
        with patch("app.services.llm.adapter.settings") as mock_settings:
            mock_settings.llm_provider = "openai"
            mock_settings.llm_api_key = "sk-test"
            mock_settings.llm_model = "gpt-4o-mini"
            adapter = get_adapter()
            assert isinstance(adapter, OpenAIAdapter)

    def test_invalid_provider(self):
        with patch("app.services.llm.adapter.settings") as mock_settings:
            mock_settings.llm_provider = "invalid"
            with pytest.raises(ValueError, match="지원하지 않는 LLM provider"):
                get_adapter()


# --- Prompt tests ---


class TestBuildAnalysisPrompt:
    def test_basic_prompt(self):
        prompt = build_analysis_prompt(
            stock_name="삼성전자",
            ticker="005930",
            market="KRX",
            current_price=71500,
            change_percent=-1.65,
            news_list=[
                {"title": "삼성전자 HBM 수주", "published_at": "2026-04-12", "source": "네이버뉴스"},
            ],
            disclosure_list=[
                {"title": "분기보고서", "disclosed_at": "2026-04-10", "disclosure_type": "정기공시"},
            ],
        )
        assert "삼성전자" in prompt
        assert "005930" in prompt
        assert "KRX" in prompt
        assert "71,500" in prompt
        assert "-1.65%" in prompt
        assert "HBM 수주" in prompt
        assert "분기보고서" in prompt
        assert "bullish" in prompt
        assert "bearish" in prompt
        assert "neutral" in prompt

    def test_truncates_news(self):
        news = [{"title": f"뉴스 {i}", "published_at": "2026-04-12", "source": "test"} for i in range(30)]
        prompt = build_analysis_prompt(
            stock_name="테스트",
            ticker="TEST",
            market="KRX",
            current_price=1000,
            change_percent=0,
            news_list=news,
            disclosure_list=[],
        )
        assert f"({MAX_NEWS_ITEMS}건)" in prompt
        assert "뉴스 0" in prompt
        assert "뉴스 19" in prompt
        assert "뉴스 20" not in prompt

    def test_empty_data(self):
        prompt = build_analysis_prompt(
            stock_name="빈종목",
            ticker="EMPTY",
            market="NASDAQ",
            current_price=None,
            change_percent=None,
            news_list=[],
            disclosure_list=[],
        )
        assert "(뉴스 없음)" in prompt
        assert "(공시 없음)" in prompt
        assert "(0건)" in prompt

    def test_json_schema_in_prompt(self):
        prompt = build_analysis_prompt(
            stock_name="테스트",
            ticker="T",
            market="KRX",
            current_price=100,
            change_percent=1.0,
            news_list=[],
            disclosure_list=[],
        )
        # JSON schema includes the required field names
        assert '"keywords"' in prompt
        assert '"daily_keywords"' in prompt
        assert '"summary"' in prompt
        assert '"feedback"' in prompt
        assert '"impact_level"' in prompt
        assert '"duration"' in prompt
