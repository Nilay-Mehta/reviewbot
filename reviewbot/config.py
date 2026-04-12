from __future__ import annotations

import os
from pathlib import Path

import tomllib

CONFIG_DIR = Path.home() / ".reviewbot"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}

    with CONFIG_FILE.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    root_scalars: list[tuple[str, object]] = []
    sections: list[tuple[str, dict]] = []

    for key, value in config.items():
        if isinstance(value, dict):
            sections.append((key, value))
        else:
            root_scalars.append((key, value))

    for key, value in root_scalars:
        lines.append(f"{key} = {_format_toml_value(value)}")

    for section, values in sections:
        if lines:
            lines.append("")
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_format_toml_value(value)}")

    content = "\n".join(lines).rstrip() + "\n"
    CONFIG_FILE.write_text(content, encoding="utf-8")


def config_exists() -> bool:
    return CONFIG_FILE.exists()


def get_api_key() -> str | None:
    config = load_config()
    groq = config.get("groq")
    if isinstance(groq, dict):
        api_key = groq.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            return api_key

    api_key = os.getenv("GROQ_API_KEY")
    return api_key or None


def get_model() -> str:
    config = load_config()
    groq = config.get("groq")
    if isinstance(groq, dict):
        model = groq.get("model")
        if isinstance(model, str) and model.strip():
            return model

    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _format_toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)

    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
