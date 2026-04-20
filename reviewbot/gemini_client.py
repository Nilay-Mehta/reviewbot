from __future__ import annotations

from dataclasses import dataclass

import httpx

from reviewbot import config


class GeminiConfigError(RuntimeError):
    pass


class GeminiConnectionError(RuntimeError):
    pass


@dataclass
class GeminiClient:
    """Thin wrapper around the Google Gemini REST API with JSON-mode enforced."""

    model: str = ""
    temperature: float = 0.2
    timeout: float = 120.0

    def __post_init__(self) -> None:
        if not self.model:
            self.model = config.get_gemini_model()
        self._api_key = config.get_gemini_api_key()
        if not self._api_key:
            raise GeminiConfigError(
                "Gemini API key not configured. Run `reviewbot setup` to get started."
            )
        self._client = httpx.Client(timeout=self.timeout)

    def complete(self, system: str, user: str) -> str:
        """Call Gemini and return the raw JSON string from the model."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}"
            f":generateContent?key={self._api_key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }
        try:
            resp = self._client.post(url, json=body)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise GeminiConnectionError(
                "Could not connect to Gemini API. Check your internet connection."
            ) from e
        except httpx.ReadTimeout as e:
            raise GeminiConnectionError(
                f"Gemini timed out after {self.timeout}s."
            ) from e
        except httpx.HTTPStatusError as e:
            raise GeminiConnectionError(
                f"Gemini returned {e.response.status_code}: {e.response.text[:200]}"
            ) from e

        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return "{}"
