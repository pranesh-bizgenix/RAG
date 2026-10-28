"""Provider-neutral clients for text generation APIs."""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Callable, Iterator

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

Message = dict[str, str]


class LLMClient(ABC):
    """Small interface implemented by every LLM provider adapter."""

    provider = "custom"
    model = ""

    @abstractmethod
    def generate(self, messages: list[Message]) -> str:
        raise NotImplementedError

    def stream(self, messages: list[Message]) -> Iterator[str]:
        """Yield the answer incrementally. Adapters without streaming return it in one piece."""
        yield self.generate(messages)


def _sse_data(response: requests.Response) -> Iterator[dict]:
    """Parse ``data:`` lines from a server-sent-events HTTP response."""
    with response:
        for raw in response.iter_lines(decode_unicode=False):
            line = raw.decode("utf-8", errors="replace").strip() if raw else ""
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                continue


class OpenAICompatibleClient(LLMClient):
    """Works with OpenAI, Groq, OpenRouter, Together, Ollama, LM Studio, and similar APIs."""

    provider = "openai-compatible"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int) -> None:
        self.api_key, self.model = api_key, model
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate(self, messages: list[Message]) -> str:
        response = requests.post(
            self.url,
            headers=self._headers(),
            json={"model": self.model, "messages": messages, "temperature": 0.2},
            timeout=self.timeout,
        )
        _raise_for_api_error(response, "LLM")
        return response.json()["choices"][0]["message"]["content"].strip()

    def stream(self, messages: list[Message]) -> Iterator[str]:
        response = _post_with_retry(
            self.url,
            headers=self._headers(),
            json={"model": self.model, "messages": messages, "temperature": 0.2, "stream": True},
            timeout=self.timeout,
            stream=True,
        )
        _raise_for_api_error(response, "LLM")
        for event in _sse_data(response):
            choices = event.get("choices") or [{}]
            if text := (choices[0].get("delta") or {}).get("content"):
                yield text


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int) -> None:
        self.api_key, self.model = api_key, model
        self.url = f"{base_url.rstrip('/')}/messages"
        self.timeout = timeout

    def _request(self, messages: list[Message], stream: bool) -> tuple[dict[str, str], dict[str, object]]:
        system = "\n\n".join(item["content"] for item in messages if item["role"] == "system")
        conversation = [item for item in messages if item["role"] in {"user", "assistant"}]
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        payload: dict[str, object] = {"model": self.model, "system": system, "messages": conversation, "max_tokens": 1024}
        if stream:
            payload["stream"] = True
        return headers, payload

    def generate(self, messages: list[Message]) -> str:
        headers, payload = self._request(messages, stream=False)
        response = requests.post(self.url, headers=headers, json=payload, timeout=self.timeout)
        _raise_for_api_error(response, "Anthropic")
        return "".join(block.get("text", "") for block in response.json()["content"]).strip()

    def stream(self, messages: list[Message]) -> Iterator[str]:
        headers, payload = self._request(messages, stream=True)
        response = _post_with_retry(self.url, headers=headers, json=payload, timeout=self.timeout, stream=True)
        _raise_for_api_error(response, "Anthropic")
        for event in _sse_data(response):
            if event.get("type") == "content_block_delta" and (text := event.get("delta", {}).get("text")):
                yield text
            elif event.get("type") == "error":
                raise RuntimeError(f"Anthropic stream error: {event.get('error')}")


class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int) -> None:
        self.api_key, self.model = api_key, model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Gemini 3 models think before answering by default, which can add minutes per reply.
        self.thinking_level = os.getenv("LLM_THINKING_LEVEL", "").strip().lower()

    def _payload(self, messages: list[Message]) -> dict[str, object]:
        system = "\n\n".join(item["content"] for item in messages if item["role"] == "system")
        contents = [
            {"role": "model" if item["role"] == "assistant" else "user", "parts": [{"text": item["content"]}]}
            for item in messages
            if item["role"] != "system"
        ]
        payload: dict[str, object] = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if self.thinking_level:
            payload["generationConfig"] = {"thinkingConfig": {"thinkingLevel": self.thinking_level}}
        return payload

    def _post(self, method: str, payload: dict[str, object], stream: bool = False) -> requests.Response:
        """Try the primary model, then each fallback while the service reports overload."""
        fallbacks = [item.strip() for item in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if item.strip()]
        response = None
        for model in dict.fromkeys([self.model, *fallbacks]):
            extra = {"stream": True} if stream else {}
            response = _post_with_retry(
                f"{self.base_url}/models/{model}:{method}",
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
                **extra,
            )
            if response.ok or response.status_code not in {429, 503}:
                break
        assert response is not None
        _raise_for_api_error(response, "Gemini")
        return response

    @staticmethod
    def _text(event: dict) -> str:
        candidates = event.get("candidates") or [{}]
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(part.get("text", "") for part in parts if not part.get("thought"))

    def generate(self, messages: list[Message]) -> str:
        response = self._post("generateContent", self._payload(messages))
        if text := self._text(response.json()).strip():
            return text
        raise RuntimeError("Gemini returned an empty response.")

    def stream(self, messages: list[Message]) -> Iterator[str]:
        response = self._post("streamGenerateContent?alt=sse", self._payload(messages), stream=True)
        for event in _sse_data(response):
            if text := self._text(event):
                yield text


def _raise_for_api_error(response: requests.Response, name: str) -> None:
    if not response.ok:
        raise RuntimeError(f"{name} request failed: {response.status_code} {response.text}")


def _post_with_retry(url: str, **kwargs: object) -> requests.Response:
    """Retry temporary API failures, timeouts, and connection errors."""

    retries = max(0, int(os.getenv("LLM_MAX_RETRIES", "2")))
    transient_statuses = {408, 429, 500, 502, 503, 504}

    # Fail fast on connection problems; wait up to LLM_TIMEOUT_SECONDS for a reply.
    read_timeout = float(kwargs.get("timeout") or 60)
    kwargs["timeout"] = (min(10.0, read_timeout), read_timeout)

    for attempt in range(retries + 1):
        try:
            response = requests.post(url, **kwargs)
        except (
            requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ConnectionError,
        ) as exc:
            if attempt == retries:
                raise RuntimeError("LLM API request failed after multiple attempts. Please try again.") from exc
            delay = min(2**attempt, 8)
            logger.warning("LLM connection issue; retry %s/%s after %ss", attempt + 1, retries, delay)
            time.sleep(delay)
            continue

        if response.status_code not in transient_statuses or attempt == retries:
            return response

        try:
            delay = float(response.headers.get("Retry-After", ""))
        except ValueError:
            delay = float(2**attempt)
        delay = min(max(delay, 0.0), 8.0)
        logger.warning("LLM returned HTTP %s; retrying after %ss", response.status_code, delay)
        response.close()
        time.sleep(delay)

    raise RuntimeError("LLM request failed unexpectedly")


ProviderFactory = Callable[[str, str, str, int], LLMClient]
PROVIDERS: dict[str, ProviderFactory] = {
    "openai-compatible": OpenAICompatibleClient,
    "anthropic": AnthropicClient,
    "gemini": GeminiClient,
}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register another provider without changing the chatbot or retrieval code."""
    PROVIDERS[name.strip().lower()] = factory


def create_llm_client() -> LLMClient | None:
    provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    if provider in {"", "none", "disabled"}:
        return None
    try:
        factory = PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Available: {', '.join(sorted(PROVIDERS))}") from exc

    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    defaults = {
        "openai-compatible": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
    }
    base_url = os.getenv("LLM_BASE_URL", "").strip() or defaults.get(provider, "")
    if not model:
        raise RuntimeError("LLM_MODEL must be configured when LLM_PROVIDER is enabled.")
    if provider in {"anthropic", "gemini"} and not api_key:
        raise RuntimeError(f"LLM_API_KEY is required for provider '{provider}'.")
    return factory(api_key, model, base_url, timeout)
