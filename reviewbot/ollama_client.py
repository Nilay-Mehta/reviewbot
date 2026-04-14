from dataclasses import dataclass
from typing import Optional

import httpx

from reviewbot import config


class OllamaConfigError(RuntimeError):
    pass


class OllamaConnectionError(RuntimeError):
    pass


@dataclass
class OllamaClient:
    """Thin wrapper around the Ollama chat API with JSON-mode enforced.

    Matches GroqClient's shape so cli.py can treat them interchangeably.
    """

    model: str = ""
    temperature: float = 0.2
    host: str = ""
    timeout: float = 300.0  # local inference can be slow

    def __post_init__(self) -> None:
        if not self.model:
            self.model = config.get_ollama_model()
        if not self.host:
            self.host = config.get_ollama_host()
        self._client = httpx.Client(base_url=self.host, timeout=self.timeout)

    def complete(self, system: str, user: str) -> str:
        """Call Ollama /api/chat and return the raw JSON string from the model."""
        try:
            resp = self._client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": self.temperature},
                },
            )
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise OllamaConnectionError(
                f"Could not connect to Ollama at {self.host}. Is it running?"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OllamaConnectionError(
                f"Ollama returned {e.response.status_code}: {e.response.text[:200]}"
            ) from e

        data = resp.json()
        return data.get("message", {}).get("content") or "{}"
