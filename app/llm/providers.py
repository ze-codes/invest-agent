from __future__ import annotations

from typing import Protocol, Iterator

from app.settings import settings


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...
    def stream(self, prompt: str) -> Iterator[str]: ...


class MockLLMProvider:
    def __init__(self) -> None:
        pass

    def complete(self, prompt: str) -> str:
        return "[mock]\n" + (prompt[:6000] if prompt else "")

    def stream(self, prompt: str) -> Iterator[str]:
        # Simple mock streaming: yield a few chunks
        txt = ("[mock_stream] " + (prompt or "")).strip()
        # Emit in ~64-char chunks
        step = 64
        for i in range(0, len(txt), step):
            yield txt[i : i + step]


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

    def stream(self, prompt: str) -> Iterator[str]:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # ImportError or others
            raise ValueError("openai package not installed. Please add 'openai' to requirements.txt") from e
        client = OpenAI(api_key=self._api_key)
        stream = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "You are a concise macro liquidity analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=800,
            stream=True,
        )
        for chunk in stream:  # type: ignore[assignment]
            try:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
            except Exception:
                continue


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
        try:
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
        except Exception:
            # Fallback to OpenAI if OpenRouter call fails
            fallback_key = settings.llm_api_key
            if not fallback_key:
                raise
            fallback_model = self._model.split("/", 1)[1] if "/" in (self._model or "") else (self._model or "gpt-4o-mini")
            fallback = OpenAILLMProvider(api_key=fallback_key, model=fallback_model)
            return fallback.complete(prompt)

    def stream(self, prompt: str) -> Iterator[str]:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise ValueError("openai package not installed. Please add 'openai' to requirements.txt") from e
        try:
            client = OpenAI(api_key=self._api_key, base_url=self._base_url)
            stream = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a concise macro liquidity analyst."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=800,
                stream=True,
            )
            for chunk in stream:  # type: ignore[assignment]
                try:
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    if content:
                        yield content
                except Exception:
                    continue
        except Exception:
            # Fallback to OpenAI if OpenRouter streaming fails
            fallback_key = settings.llm_api_key
            if not fallback_key:
                raise
            fallback_model = self._model.split("/", 1)[1] if "/" in (self._model or "") else (self._model or "gpt-4o-mini")
            fallback = OpenAILLMProvider(api_key=fallback_key, model=fallback_model)
            yield from fallback.stream(prompt)


def get_provider() -> LLMProvider:
    provider = (settings.llm_provider or "mock").lower()
    if provider in ("mock", "none", "dev"):
        return MockLLMProvider()
    if provider in ("openai",):
        return OpenAILLMProvider(api_key=settings.llm_api_key, model=settings.llm_model)
    if provider in ("openrouter",):
        return OpenRouterProvider(api_key=settings.openrouter_api_key or settings.llm_api_key, model=settings.llm_model, base_url=settings.llm_base_url)
    return MockLLMProvider()
