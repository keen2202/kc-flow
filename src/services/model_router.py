"""Unified model router — abstracts LLM provider differences behind a single interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator
import time

import httpx
import structlog

from src.core.exceptions import LLMCallError, CircuitBreakerOpenError

logger = structlog.get_logger()


# ──────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    model_id: str                     # e.g. "gpt-4o", "claude-opus-4-7"
    provider: ModelProvider
    display_name: str
    context_window: int = 128000
    supports_vision: bool = False
    supports_streaming: bool = True
    input_price_per_1k: float = 0.0   # USD per 1000 input tokens
    output_price_per_1k: float = 0.0


@dataclass
class ChatMessage:
    role: str       # system / user / assistant
    content: str


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_ms: int
    model: str
    finish_reason: str  # stop / length / tool_calls / error
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamingChunk:
    text: str
    is_final: bool = False
    finish_reason: str | None = None


# ──────────────────────────────────────────────
# Provider Abstraction
# ──────────────────────────────────────────────


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamingChunk]:
        ...


# ──────────────────────────────────────────────
# OpenAI Provider
# ──────────────────────────────────────────────


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible API provider."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=120.0)

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        start = time.monotonic()
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        resp = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        choice = data["choices"][0]

        return LLMResponse(
            text=choice["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            duration_ms=int((time.monotonic() - start) * 1000),
            model=data.get("model", model),
            finish_reason=choice.get("finish_reason", "stop"),
            raw_response=data,
        )

    async def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamingChunk]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with self.client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    yield StreamingChunk(text="", is_final=True)
                    break
                import json
                chunk_data = json.loads(data_str)
                delta = chunk_data["choices"][0].get("delta", {})
                content = delta.get("content", "")
                finish = chunk_data["choices"][0].get("finish_reason")
                yield StreamingChunk(text=content, is_final=finish is not None, finish_reason=finish)


# ──────────────────────────────────────────────
# Anthropic Provider
# ──────────────────────────────────────────────


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=120.0)

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        start = time.monotonic()

        # Anthropic uses system as top-level param
        system_msg = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_msg:
            payload["system"] = system_msg

        resp = await self.client.post(
            f"{self.base_url}/messages",
            json=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})

        text_content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_content += block["text"]

        return LLMResponse(
            text=text_content,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            duration_ms=int((time.monotonic() - start) * 1000),
            model=data.get("model", model),
            finish_reason=data.get("stop_reason", "stop"),
            raw_response=data,
        )

    async def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamingChunk]:
        system_msg = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system_msg:
            payload["system"] = system_msg

        async with self.client.stream(
            "POST",
            f"{self.base_url}/messages",
            json=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            import json
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                event_type = event.get("type")
                if event_type == "content_block_delta":
                    text = event.get("delta", {}).get("text", "")
                    yield StreamingChunk(text=text)
                elif event_type == "message_stop":
                    yield StreamingChunk(text="", is_final=True, finish_reason="stop")
                    break


# ──────────────────────────────────────────────
# Model Router
# ──────────────────────────────────────────────


class ModelRouter:
    """Unified model router — routes calls to appropriate provider, handles fallbacks and circuit breakers."""

    # Default model configurations
    DEFAULT_MODELS: dict[str, ModelConfig] = {
        "gpt-4o": ModelConfig(
            model_id="gpt-4o", provider=ModelProvider.OPENAI,
            display_name="GPT-4o", context_window=128000,
            supports_vision=True, input_price_per_1k=0.0025, output_price_per_1k=0.01,
        ),
        "gpt-4.1": ModelConfig(
            model_id="gpt-4.1", provider=ModelProvider.OPENAI,
            display_name="GPT-4.1", context_window=1047576,
            supports_vision=True, input_price_per_1k=0.002, output_price_per_1k=0.008,
        ),
        "claude-opus-4-7": ModelConfig(
            model_id="claude-opus-4-7", provider=ModelProvider.ANTHROPIC,
            display_name="Claude Opus 4.7", context_window=200000,
            supports_vision=True, input_price_per_1k=0.015, output_price_per_1k=0.075,
        ),
        "claude-sonnet-4-6": ModelConfig(
            model_id="claude-sonnet-4-6", provider=ModelProvider.ANTHROPIC,
            display_name="Claude Sonnet 4.6", context_window=200000,
            supports_vision=True, input_price_per_1k=0.003, output_price_per_1k=0.015,
        ),
    }

    def __init__(self, openai_key: str = "", anthropic_key: str = ""):
        self._providers: dict[ModelProvider, LLMProvider] = {}
        self._models: dict[str, ModelConfig] = dict(self.DEFAULT_MODELS)
        self._circuit_breakers: dict[str, Any] = {}
        self._usage: dict[str, dict[str, int]] = {}

        if openai_key:
            self._providers[ModelProvider.OPENAI] = OpenAIProvider(api_key=openai_key)
        if anthropic_key:
            self._providers[ModelProvider.ANTHROPIC] = AnthropicProvider(api_key=anthropic_key)

    def register_model(self, config: ModelConfig) -> None:
        """Register a custom model configuration."""
        self._models[config.model_id] = config

    def get_model_config(self, model_id: str) -> ModelConfig | None:
        return self._models.get(model_id)

    async def call_llm(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        fallback_model: str | None = None,
    ) -> LLMResponse:
        """Call an LLM model with automatic fallback on failure."""
        try:
            return await self._call(model, messages, temperature, max_tokens, response_format)
        except Exception as primary_error:
            if fallback_model:
                logger.warning("Primary model failed, trying fallback", primary=model, fallback=fallback_model, error=str(primary_error))
                try:
                    return await self._call(fallback_model, messages, temperature, max_tokens, response_format)
                except Exception as fallback_error:
                    raise LLMCallError(
                        message=f"Both primary ({model}) and fallback ({fallback_model}) failed",
                        node_id="",
                        model=model,
                        cause=fallback_error,
                    )
            raise LLMCallError(message=str(primary_error), node_id="", model=model, cause=primary_error)

    async def _call(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None,
    ) -> LLMResponse:
        config = self._models.get(model)
        if not config:
            raise ValueError(f"Unknown model: {model}. Available: {list(self._models.keys())}")

        provider = self._providers.get(config.provider)
        if not provider:
            raise ValueError(f"Provider '{config.provider.value}' not configured for model '{model}'")

        response = await provider.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

        # Track usage
        self._track_usage(model, response)
        return response

    async def call_llm_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamingChunk]:
        """Stream LLM responses chunk by chunk.

        Yields StreamingChunk objects as they arrive from the provider.
        """
        config = self._models.get(model)
        if not config:
            raise ValueError(f"Unknown model: {model}. Available: {list(self._models.keys())}")

        provider = self._providers.get(config.provider)
        if not provider:
            raise ValueError(f"Provider '{config.provider.value}' not configured for model '{model}'")

        async for chunk in provider.chat_stream(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    def _track_usage(self, model: str, response: LLMResponse) -> None:
        """Track token usage per model."""
        if model not in self._usage:
            self._usage[model] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        self._usage[model]["calls"] += 1
        self._usage[model]["input_tokens"] += response.input_tokens
        self._usage[model]["output_tokens"] += response.output_tokens

    def get_usage_stats(self, model: str | None = None) -> dict[str, Any]:
        """Get usage statistics for a specific model or all models."""
        if model:
            return self._usage.get(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        return dict(self._usage)
