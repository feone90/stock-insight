from abc import ABC, abstractmethod

from openai import AsyncAzureOpenAI, AsyncOpenAI

from app.config import settings


class LLMAdapter(ABC):
    """LLM 호출 인터페이스. 어댑터 패턴으로 모델 교체 가능."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """프롬프트를 전송하고 응답 텍스트를 반환한다."""

    @abstractmethod
    async def generate_json(self, prompt: str) -> str:
        """프롬프트를 전송하고 JSON 응답을 반환한다."""


class AzureOpenAIAdapter(LLMAdapter):
    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
        api_version: str = "2024-12-01-preview",
    ):
        self.deployment = deployment or settings.llm_deployment
        self.client = AsyncAzureOpenAI(
            azure_endpoint=endpoint or settings.llm_endpoint,
            api_key=api_key or settings.llm_api_key,
            api_version=api_version,
        )

    async def generate(self, prompt: str) -> str:
        resp = await self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""

    async def generate_json(self, prompt: str) -> str:
        resp = await self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


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
