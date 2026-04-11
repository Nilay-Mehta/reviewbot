import os
from dataclasses import dataclass

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class GroqConfigError(RuntimeError):
    pass


@dataclass
class GroqClient:
    """Thin wrapper around the Groq chat API with JSON-mode enforced.

    Kept intentionally small so a second backend (Ollama, Gemini) can be
    added later behind the same `complete(system, user) -> str` shape.
    """

    model: str = DEFAULT_MODEL
    temperature: float = 0.2

    def __post_init__(self) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise GroqConfigError(
                "GROQ_API_KEY not set. Copy .env.example to .env and add your key."
            )
        self._client = Groq(api_key=api_key)

    def complete(self, system: str, user: str) -> str:
        """Call Groq and return the raw JSON string from the model."""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or "{}"
