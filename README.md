# ReviewBot

ReviewBot is a lightweight Python CLI that reviews git diffs with an LLM and reports structured findings in the terminal. The codebase stays intentionally small: git capture, diff splitting, prompt construction, model calls, schema validation, and reporting are isolated so you can keep shipping quickly now without boxing yourself out of a richer cloud-versus-local backend later.

## Why

- Local-first option: the client boundary is thin enough to swap Groq for a local model backend later without rewriting the CLI.
- Schema-validated LLM output: every model response is parsed into strict Pydantic v2 models, with a repair path when JSON comes back malformed.
- Git-native workflow: the tool reviews staged changes, the last commit, or a single file directly from git diffs instead of inventing a separate review format.

## Install

```bash
pip install -e .
```

Then create your environment file:

```bash
copy .env.example .env
```

Set `GROQ_API_KEY` in `.env`, and optionally override `GROQ_MODEL` if you do not want the default Groq model.

## Usage

Review staged changes:

```bash
reviewbot
```

Review the last commit:

```bash
reviewbot --last
```

Review one file:

```bash
reviewbot --file path/to/file.py
```

## Architecture

The pipeline is git diff capture -> per-file chunks -> prompt builder -> Groq in JSON mode -> parse and repair -> rich terminal reporter. Each file is reviewed independently so line references stay grounded, and the model output is validated against strict Pydantic schemas before it is rendered. Rate-limit handling is intentionally kept in `cli.py`, where requests run in a synchronous loop with backoff and a 3 second inter-call delay to stay predictable under free-tier limits.

## Rate Limit Safety

Groq's free tier is treated as roughly 12k tokens per minute and 30 requests per minute, so the bot avoids bursty fan-out. It processes files synchronously, waits 3 seconds between calls, backs off for 10 seconds on HTTP 429 responses, and gives up after 3 retries instead of hammering the API. That keeps the behavior simple, understandable, and much less likely to fail mid-review on larger staged changes.

## Tech

- Python
- Typer
- Rich
- Pydantic v2
- Groq SDK
- Llama 3.3 70B
