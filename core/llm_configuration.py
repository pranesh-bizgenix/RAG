"""Validate language-model settings and read legacy file-based configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SERVICES: tuple[dict[str, Any], ...] = (
    {
        "id": "openai",
        "label": "OpenAI",
        "provider": "openai-compatible",
        "base_url": "https://api.openai.com/v1",
        "models": (
            ("gpt-6.1-sol", "GPT-6.1 Sol"),
            ("gpt-6-astra", "GPT-6 Astra"),
            ("gpt-6.1-terra", "GPT-6.1 Terra"),
            ("gpt-6-luna", "GPT-6 Luna"),
        ),
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "models": (
            ("claude-sonnet-5", "Claude Sonnet 5"),
            ("claude-opus-5", "Claude Opus 5"),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
        ),
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "provider": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": (
            ("gemini-3.8-flash", "Gemini 3.8 Flash"),
            ("gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
            ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),
            ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ),
    },
    {
        "id": "xai",
        "label": "xAI (Grok)",
        "provider": "openai-compatible",
        "base_url": "https://api.x.ai/v1",
        "models": (
            ("grok-4.7", "Grok 4.7"),
            ("grok-4.6", "Grok 4.6"),
        ),
    },
    {
        "id": "groq",
        "label": "Groq",
        "provider": "openai-compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "models": (
            ("openai/gpt-oss-120b", "GPT-OSS 120B"),
            ("openai/gpt-oss-20b", "GPT-OSS 20B"),
            ("qwen/qwen3.8-27b", "Qwen 3.8 27B"),
        ),
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "provider": "openai-compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "models": (),
    },
    {
        "id": "custom",
        "label": "Custom / local API",
        "provider": "openai-compatible",
        "base_url": "http://localhost:11434/v1",
        "models": (),
    },
)

SERVICE_BY_ID = {item["id"]: item for item in SERVICES}


def public_catalog() -> list[dict[str, Any]]:
    """Return browser-safe provider metadata."""
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "base_url": item["base_url"],
            "models": [{"id": model_id, "label": label} for model_id, label in item["models"]],
        }
        for item in SERVICES
    ]


def configuration_from_environment() -> dict[str, str] | None:
    """Return a validated configuration from the deployment environment."""
    provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    if provider in {"", "none", "disabled"}:
        return None
    model = os.getenv("LLM_MODEL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    service_id = provider if provider in SERVICE_BY_ID else ""
    if provider == "openai-compatible" and not base_url:
        service_id = "openai"
    if not service_id:
        for service in SERVICES:
            if service["provider"] == provider and base_url.rstrip("/") == str(service["base_url"]).rstrip("/"):
                service_id = str(service["id"])
                break
    if not service_id:
        service_id = "custom" if provider == "openai-compatible" else provider
    return validate_configuration(
        {"service": service_id, "model": model, "api_key": api_key, "base_url": base_url}
    )


def load_configuration(path: Path) -> dict[str, str] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return {key: str(payload.get(key, "")).strip() for key in ("service", "provider", "model", "api_key", "base_url")}


def validate_configuration(payload: dict[str, Any]) -> dict[str, str] | None:
    service_id = str(payload.get("service", "")).strip().lower()
    if service_id in {"", "none", "disabled"}:
        return None
    service = SERVICE_BY_ID.get(service_id)
    if not service:
        raise ValueError("Choose a supported LLM provider.")
    model = str(payload.get("model", "")).strip()
    api_key = str(payload.get("api_key", "")).strip()
    base_url = str(payload.get("base_url", "")).strip() or str(service["base_url"])
    if not model or len(model) > 160:
        raise ValueError("Choose or enter a valid model name.")
    if not api_key or len(api_key) > 4096:
        raise ValueError("Enter the API key for this provider.")
    if not base_url.startswith(("https://", "http://")) or len(base_url) > 500:
        raise ValueError("Base URL must start with http:// or https://.")
    return {
        "service": service_id,
        "provider": str(service["provider"]),
        "model": model,
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
    }


def save_configuration(path: Path, configuration: dict[str, str] | None) -> None:
    """Atomically save a secret-bearing configuration with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if configuration is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(configuration, indent=2), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
