from __future__ import annotations

from typing import Protocol

from app.settings import settings


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...


class MockLLMProvider:
    def __init__(self) -> None:
        pass

    def complete(self, prompt: str) -> str:
        return "[mock]\n" + (prompt[:6000] if prompt else "")


class OpenAILLMProvider:
    def __init__(self, api_key: str | None, model: str | None) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is required for OpenAI provider")
        self._api_key = api_key
        self._model = model or "gpt-4o-mini"

    def complete(self, prompt: str) -> str:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # ImportError or others
            raise ValueError("openai package not installed. Please add 'openai' to requirements.txt") from e

        client = OpenAI(api_key=self._api_key)
        # Use chat completions for broad compatibility
        resp = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "You are a concise macro liquidity analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        content = resp.choices[0].message.content or ""
        return content


class OpenRouterProvider:
    def __init__(self, api_key: str | None, model: str | None, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for openrouter provider")
        self._api_key = api_key
        self._model = model or "openai/gpt-4o-mini"
        self._base_url = base_url or "https://openrouter.ai/api/v1"

    def complete(self, prompt: str) -> str:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise ValueError("openai package not installed. Please add 'openai' to requirements.txt") from e
        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        resp = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "You are a concise macro liquidity analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        content = resp.choices[0].message.content or ""
        return content


class LangChainOpenRouterProvider:
    def __init__(self, api_key: str | None, model: str | None, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for langchain_openrouter provider")
        self._api_key = api_key
        self._model = model or "openai/gpt-4o-mini"
        self._base_url = base_url or "https://openrouter.ai/api/v1"

    def complete(self, prompt: str) -> str:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore
        except Exception as e:
            raise ValueError("langchain_openai package not installed. Please add 'langchain-openai' to requirements.txt") from e
        llm = ChatOpenAI(
            model=self._model,
            openai_api_key=self._api_key,
            openai_api_base=self._base_url,
            temperature=0.2,
            max_tokens=800,
        )
        msg = llm.invoke(prompt)
        return getattr(msg, "content", str(msg))


def get_provider() -> LLMProvider:
    provider = (settings.llm_provider or "mock").lower()
    if provider in ("mock", "none", "dev"):
        return MockLLMProvider()
    if provider in ("openai",):
        return OpenAILLMProvider(api_key=settings.llm_api_key, model=settings.llm_model)
    if provider in ("openrouter",):
        return OpenRouterProvider(api_key=settings.openrouter_api_key or settings.llm_api_key, model=settings.llm_model, base_url=settings.llm_base_url)
    if provider in ("langchain_openrouter", "lc_openrouter"):
        return LangChainOpenRouterProvider(api_key=settings.openrouter_api_key or settings.llm_api_key, model=settings.llm_model, base_url=settings.llm_base_url)
    # Default to mock for unknown values to avoid breaking local runs
    return MockLLMProvider()


