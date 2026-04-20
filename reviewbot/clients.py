from __future__ import annotations

from typing import Protocol

from reviewbot import config


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


def make_client(model_override: str | None = None) -> LLMClient:
    """Factory: returns the configured backend client."""
    backend = config.get_backend()
    if backend == "ollama":
        from reviewbot.ollama_client import OllamaClient

        return OllamaClient(model=model_override or "")
    if backend == "gemini":
        from reviewbot.gemini_client import GeminiClient

        if model_override:
            return GeminiClient(model=model_override)
        return GeminiClient()
    from reviewbot.groq_client import GroqClient

    if model_override:
        return GroqClient(model=model_override)
    return GroqClient()
