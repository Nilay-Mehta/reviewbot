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

## Getting Started

### 1. Prerequisites

- **Python 3.11+** — check with `python --version`
- **pipx** — install with `python -m pip install --user pipx && python -m pipx ensurepath` (then reopen your terminal)
- **Git** — any recent version
- **Groq API key** (free) — sign up at https://console.groq.com/keys, click "Create API Key", and copy it

### 2. Install ReviewBot

```bash
pipx install git+https://github.com/Nilay-Mehta/reviewbot.git
```

Or from source:

```bash
git clone https://github.com/Nilay-Mehta/reviewbot.git
cd reviewbot
pipx install -e .
```

After installation, the `reviewbot` command is available globally from any terminal window.

### 3. First Run Setup

Open any terminal and type:

```bash
reviewbot
```

The setup wizard will launch automatically and walk you through:

1. **Backend selection** — choose Groq (cloud, free tier) or Ollama (local, coming soon)
2. **API key** — paste the Groq key you copied earlier
3. **Model** — press Enter to use the default (Llama 3.3 70B) or type a different model name
4. **Connection test** — verifies your key works before saving

Your settings are saved to `~/.reviewbot/config.toml`. You only do this once — after setup, `reviewbot` goes straight to reviewing code. To reconfigure later, run `reviewbot setup`.

### 4. Review Your First Diff

```bash
cd your-project
git add .
reviewbot
```

That's it. ReviewBot reads your staged changes, sends each file to the LLM, and prints a severity-ranked review table in your terminal.

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
