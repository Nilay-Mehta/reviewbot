# ReviewBot (Under-Production)

AI-powered code reviewer that runs from your terminal. Point it at any git repo, and it reviews staged changes or recent commits using either Groq or Ollama, returning structured, severity-ranked comments with concrete fix suggestions.

![ReviewBot Demo](assets/demo.png)

## Features

- **One-command setup** - interactive wizard configures everything on first run
- **Zero-friction review** - just type `reviewbot` inside any git repo
- **Schema-validated output** - every LLM response is parsed into strict Pydantic v2 models with automatic repair on malformed JSON
- **Severity-ranked comments** - blocker, major, minor, nit - with categories (`bug`, `security`, `perf`, `style`, `design`, `docs`)
- **Git-native** - reviews staged changes, the last commit, commit ranges, or a single file directly from unified diffs
- **Multiple review modes** - `errors`, `security`, `perf`, `style`, `explain`, and `detail`
- **Per-repo memory** - stores review results in `.reviewbot/history` with 30-entry rotation so follow-up reviews can go deeper
- **Team-gap review support** - review the last `N` commits, commits since a ref, or each commit separately
- **One-off model override** - use `--model <name>` to try a different model for a single run
- **Persistent backend switching** - use `reviewbot switch` to change backend/model without re-running full setup
- **Rate-limit safe** - synchronous processing with 3s inter-call throttle, 10s backoff on 429, max 3 retries
- **Three backend options** - Groq for fast cloud inference, Ollama for local/offline review, and Gemini via Google AI Studio

## Getting Started

### 1. Prerequisites

- **Python 3.11+** - check with `python --version`
- **pipx** - install with `python -m pip install --user pipx && python -m pipx ensurepath` (then reopen your terminal)
- **Git** - any recent version
- **Groq API key** (free) if you plan to use the cloud backend - get one at [console.groq.com/keys](https://console.groq.com/keys)
- **Ollama** if you plan to use the local backend - install from [ollama.com](https://ollama.com)

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

The setup wizard launches automatically and walks you through:

1. **Backend selection** - choose Groq (cloud, free tier), Ollama (local), or Gemini (cloud, free tier)
2. **Credentials / host** - enter your Groq/Gemini API key or confirm your Ollama host
3. **Model** - press Enter to use the default model or type a different one
4. **Connection test** - verifies the backend works before saving

Your settings are saved to `~/.reviewbot/config.toml`. You only do this once. To reconfigure later, run `reviewbot setup` or `reviewbot switch`.

### 4. Review Your First Diff

```bash
cd your-project
git add .
reviewbot
```

That's it. ReviewBot reads your staged changes, sends each file to the configured backend, and prints a severity-ranked review report in your terminal.

## Usage

### Quick Reference

| Command / Flag | What it does |
| --- | --- |
| `reviewbot` | Review staged changes |
| `reviewbot --last` | Review the last commit |
| `reviewbot --file path/to/file.py` | Review one staged file |
| `reviewbot --commits 3` | Review the last 3 commits as one combined diff |
| `reviewbot --since main` | Review all commits from `main` to `HEAD` |
| `reviewbot --per-commit` | Review each commit separately; requires `--last`, `--commits`, or `--since` |
| `reviewbot --max-files 10` | Skip review if the diff touches more than 10 files |
| `reviewbot --mode security` | Run a mode-specific review |
| `reviewbot --model qwen/qwen3-32b` | Override the model for just this run |
| `reviewbot setup` | Run first-time/full setup |
| `reviewbot switch` | Change backend/model persistently |

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

Review the last 3 commits as one combined diff:

```bash
reviewbot --commits 3
```

Review all commits since a ref:

```bash
reviewbot --since main
```

Review recent commits one commit at a time:

```bash
reviewbot --commits 3 --per-commit
```

Review all commits since a ref, one commit at a time:

```bash
reviewbot --since main --per-commit
```

Skip review if a large diff touches too many files:

```bash
reviewbot --commits 5 --max-files 20
```

Run a specific review mode:

```bash
reviewbot --mode security
reviewbot --mode explain
reviewbot --mode detail
```

Override the model for a single run:

```bash
reviewbot --model qwen/qwen3-32b --last
```

Full command reference:

- See [COMMANDS.md](COMMANDS.md) for the complete command guide and examples.

Re-run setup anytime:

```bash
reviewbot setup
```

Switch backend or model without re-entering everything:

```bash
reviewbot switch
```

Uninstall ReviewBot:

```bash
pipx uninstall reviewbot
```

## Review Modes

- **errors** - default mode for bugs, logic issues, edge cases, and missing error handling
- **security** - only security findings such as injection risks, secrets, auth gaps, and unsafe subprocess/file handling
- **perf** - only performance concerns such as unnecessary round-trips, poor complexity, or wasteful allocations
- **style** - only readability and style issues
- **explain** - no critique; summarizes what each diff does in plain English
- **detail** - follow-up review mode that injects recent repo-local review history so follow-up reviews can reference prior findings

## Review Sources

- **staged changes** - default with `reviewbot`
- **last commit** - `reviewbot --last`
- **single file** - `reviewbot --file path/to/file.py`
- **last N commits** - `reviewbot --commits 3`
- **since a ref** - `reviewbot --since main`
- **per-commit review** - add `--per-commit` to `--last`, `--commits`, or `--since`

Rules:
- only one source flag can be used at a time: `--last`, `--commits`, `--since`, or `--file`
- `--per-commit` requires `--last`, `--commits`, or `--since`
- `--max-files N` skips the review if the diff touches more than `N` files

## How It Works

```text
git diff --cached / git show / commit range diff / file diff
      |
      v
  diff_parser ---- split unified diff into per-file chunks
      |
      v
  history ------- load recent reviews for detail mode (optional)
      |
      v
  prompt_builder -- inject diff, schema, mode prompt, and prior context
      |
      v
  clients ------- choose GroqClient or OllamaClient
      |
      v
  llm backend ---- call the configured model in JSON mode
      |
      v
  output_parser --- validate against Pydantic schema, repair if needed
      |
      v
  history ------- save successful reviews to .reviewbot/history
      |
      v
  gitignore ----- auto-add .reviewbot/ to .gitignore
      |
      v
  reporter ------ Rich report with colored severity + exit code
```

Each file is reviewed independently so line references stay grounded. ReviewBot saves successful reviews to `.reviewbot/history` as sha256-keyed JSON with 30-entry rotation, and auto-adds `.reviewbot/` to `.gitignore`. In `detail` mode, it loads recent high-severity findings and injects that context so follow-up reviews can avoid repeating old feedback and go deeper on new issues.

## Backends And Models

### Available Backends

- **Groq** - cloud backend with fast inference and JSON-mode responses
- **Ollama** - local/offline backend for models running on your machine
- **Gemini** - Google Gemini REST backend using API-key auth and JSON-mode responses

### Available Groq Models

- `llama-3.3-70b-versatile` - default
- `qwen/qwen3-32b`
- `meta-llama/llama-4-scout-17b-16e-instruct`

### Switching Models

- Use `reviewbot switch` to change backend/model persistently
- Use `reviewbot --model <name>` for a one-off override without changing saved config

## Pre-commit Hook

Auto-review on every commit:

```bash
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Commits with blocker or major findings are blocked. Bypass with `git commit --no-verify`.

## Tech Stack

- **Python 3.11+**
- **Typer** - CLI framework
- **Rich** - terminal formatting
- **Pydantic v2** - schema validation
- **Groq SDK** - cloud LLM client
- **Ollama HTTP API** - local LLM backend
- **Llama 3.3 70B** / local code models - review engines

## License

GPL-3.0
