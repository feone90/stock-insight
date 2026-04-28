from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

import httpx
from openai import AsyncOpenAI

from app.config import settings


class LLMAdapter(ABC):
    """LLM 호출 인터페이스. 어댑터 패턴으로 모델 교체 가능."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """프롬프트를 전송하고 응답 텍스트를 반환한다."""

    @abstractmethod
    async def generate_json(self, prompt: str) -> str:
        """프롬프트를 전송하고 JSON 응답을 반환한다."""

    async def chat_with_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> AsyncGenerator[dict, None]:
        """Tool-calling 지원 어댑터만 구현. 기본은 NotImplementedError."""
        raise NotImplementedError("This adapter does not support tool calling")
        yield  # pragma: no cover


class AzureOpenAIAdapter(LLMAdapter):
    """Azure AI Foundry Responses API 어댑터."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
    ):
        self.endpoint = endpoint or settings.llm_endpoint
        self.api_key = api_key or settings.llm_api_key
        self.deployment = deployment or settings.llm_deployment

    async def _call(self, prompt: str, json_mode: bool = False) -> str:
        body: dict = {
            "model": self.deployment,
            "input": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        if json_mode:
            body["text"] = {"format": {"type": "json_object"}}

        async with httpx.AsyncClient(timeout=60) as client:
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
        # Concatenate all output_text chunks across all message items —
        # Foundry can split a long response across multiple chunks; returning
        # only the first one truncates JSON output mid-document.
        texts: list[str] = []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        texts.append(content.get("text", ""))
        return "".join(texts)

    async def generate(self, prompt: str) -> str:
        return await self._call(prompt)

    async def generate_json(self, prompt: str) -> str:
        return await self._call(prompt, json_mode=True)

    async def chat_with_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> AsyncGenerator[dict, None]:
        """Foundry Responses API로 tool-calling 요청, 결과를 async generator로 yield.

        Yields:
          {"type": "text", "content": "..."}
          {"type": "function_call", "name": "...", "arguments": {...}, "call_id": "..."}
          {"type": "done"}
        """
        import json as _json
        import logging
        _logger = logging.getLogger(__name__)

        # Responses API: system message → "instructions" field, not in input
        instructions = None
        input_messages = []
        for m in messages:
            if m.get("role") == "system":
                instructions = m["content"]
            elif m.get("type") in ("function_call", "function_call_output"):
                input_messages.append(m)  # tool call/result items pass through
            else:
                input_messages.append(m)

        body: dict = {
            "model": self.deployment,
            "input": input_messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.3,
        }
        if instructions:
            body["instructions"] = instructions

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.endpoint,
                json=body,
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                _logger.error("Foundry API error %s: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()

        data = resp.json()
        for item in data.get("output", []):
            item_type = item.get("type")
            if item_type == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        yield {"type": "text", "content": content.get("text", "")}
            elif item_type == "function_call":
                raw_args = item.get("arguments", "{}")
                try:
                    args = _json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except _json.JSONDecodeError:
                    args = {}
                yield {
                    "type": "function_call",
                    "name": item.get("name", ""),
                    "arguments": args,
                    "call_id": item.get("call_id", ""),
                }

        yield {"type": "done"}


class OpenAIAdapter(LLMAdapter):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.model = model or settings.llm_model or "gpt-4o-mini"
        self.client = AsyncOpenAI(api_key=api_key or settings.llm_api_key)

    async def generate(self, prompt: str) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""

    async def generate_json(self, prompt: str) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


def get_adapter() -> LLMAdapter:
    """config 설정에 따라 적절한 LLM 어댑터를 반환한다."""
    provider = settings.llm_provider
    if provider == "azure_openai":
        return AzureOpenAIAdapter()
    if provider == "openai":
        return OpenAIAdapter()
    raise ValueError(f"지원하지 않는 LLM provider: {provider}")
