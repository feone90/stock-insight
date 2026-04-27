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


def _mock_foundry_response(text: str | None):
    """Foundry Responses API 응답 형태 mock. text=None → 빈 출력."""
    if text is None:
        body = {"output": []}
    else:
        body = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": text}],
                }
            ]
        }
    resp = MagicMock()
    resp.json.return_value = body
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


def _patch_httpx(mock_resp):
    """httpx.AsyncClient context manager + post() 를 패치하는 헬퍼."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return patch("app.services.llm.adapter.httpx.AsyncClient", return_value=cm), mock_client


class TestAzureOpenAIAdapter:
    @pytest.mark.asyncio
    async def test_generate(self):
        adapter = AzureOpenAIAdapter(
            endpoint="https://x.openai.azure.com/responses",
            api_key="k",
            deployment="gpt-4o-mini",
        )
        patch_ctx, mock_client = _patch_httpx(_mock_foundry_response("hello"))

        with patch_ctx:
            result = await adapter.generate("test prompt")

        assert result == "hello"
        mock_client.post.assert_called_once()
        body = mock_client.post.call_args.kwargs["json"]
        assert body["model"] == "gpt-4o-mini"
        assert body["input"] == [{"role": "user", "content": "test prompt"}]
        assert "text" not in body  # generate() — JSON 모드 아님

    @pytest.mark.asyncio
    async def test_generate_json(self):
        adapter = AzureOpenAIAdapter(
            endpoint="https://x.openai.azure.com/responses",
            api_key="k",
            deployment="gpt-4o-mini",
        )
        patch_ctx, mock_client = _patch_httpx(_mock_foundry_response('{"keywords": []}'))

        with patch_ctx:
            result = await adapter.generate_json("test prompt")

        assert result == '{"keywords": []}'
        body = mock_client.post.call_args.kwargs["json"]
        assert body["text"] == {"format": {"type": "json_object"}}

    @pytest.mark.asyncio
    async def test_generate_empty_content(self):
        adapter = AzureOpenAIAdapter(
            endpoint="https://x.openai.azure.com/responses",
            api_key="k",
            deployment="test",
        )
        patch_ctx, _ = _patch_httpx(_mock_foundry_response(None))

        with patch_ctx:
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
