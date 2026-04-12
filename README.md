# ReviewBot

AI-powered code reviewer that runs locally from your terminal. Point it at any git repo, and it reviews your staged changes using Llama 3.3 70B via Groq — returning structured, severity-ranked comments with concrete fix suggestions.

![ReviewBot Demo](assets/demo.png)

## Features

- **One-command setup** — interactive wizard configures everything on first run
- **Zero-friction review** — just type `reviewbot` inside any git repo
- **Schema-validated output** — every LLM response is parsed into strict Pydantic v2 models with automatic repair on malformed JSON
- **Severity-ranked comments** — blocker, major, minor, nit — with categories (bug, security, perf, style, design, docs)
- **Git-native** — reviews staged changes, last commit, or a single file directly from unified diffs
- **Rate-limit safe** — synchronous processing with 3s inter-call throttle, 10s backoff on 429, max 3 retries
- **Swappable backend** — designed for easy addition of Ollama (local/offline) or Gemini backends

## Install

```bash
pipx install git+https://github.com/Nilay-Mehta/reviewbot.git
```

Or from source:

```bash
git clone https://github.com/Nilay-Mehta/reviewbot.git
cd reviewbot
pipx install -e .
```

## First Run

```bash
reviewbot
```

On first launch, the setup wizard walks you through backend selection and API key configuration. Your settings are saved to `~/.reviewbot/config.toml` — no manual env vars or `.env` files needed.

## Usage

Review staged changes (default):

```bash
reviewbot
```

Review the last commit:

```bash
reviewbot --last
```

Review a single file:

```bash
reviewbot --file path/to/file.py
```

Re-run setup anytime:

```bash
reviewbot setup
```

## How It Works

```
git diff --cached
      |
      v
  diff_parser ---- split into per-file chunks
      |
      v
  prompt_builder -- inject chunk + JSON schema into prompt
      |
      v
  groq_client ---- call Llama 3.3 70B (JSON mode, temp 0.2)
      |
      v
  output_parser --- validate against Pydantic schema, repair if needed
      |
      v
  reporter -------- Rich table with colored severity + exit code
```

Each file is reviewed independently so line references stay grounded. The pipeline is synchronous with built-in rate-limit protection for Groq's free tier (12k TPM / 30 RPM).

## Pre-commit Hook

Auto-review on every commit:

```bash
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Commits with blocker or major findings are blocked. Bypass with `git commit --no-verify`.

## Tech Stack

- **Python 3.11+**
- **Typer** — CLI framework
- **Rich** — terminal formatting
- **Pydantic v2** — schema validation
- **Groq SDK** — LLM API client
- **Llama 3.3 70B** — code review model

## License

MIT
