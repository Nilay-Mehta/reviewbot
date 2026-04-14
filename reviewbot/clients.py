from __future__ import annotations

from typing import Protocol

from reviewbot import config


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


def make_client() -> LLMClient:
    """Factory: returns the configured backend client."""
    backend = config.get_backend()
    if backend == "ollama":
        from reviewbot.ollama_client import OllamaClient

        return OllamaClient()
    from reviewbot.groq_client import GroqClient

    return GroqClient()
