# ReviewBot Command Guide

This guide lists the main commands supported by ReviewBot and when to use them.

## Core Commands

Review staged changes in the current git repo:

```bash
reviewbot
```

Review the last commit:

```bash
reviewbot --last
```

Review only one staged file:

```bash
reviewbot --file path/to/file.py
```

Review the last `N` commits as one combined diff:

```bash
reviewbot --commits 3
reviewbot -n 3
```

Review every commit since a ref:

```bash
reviewbot --since main
reviewbot --since HEAD~5
```

Run the setup wizard again:

```bash
reviewbot setup
```

Uninstall the globally installed CLI:

```bash
pipx uninstall reviewbot
```

## Review Modes

Default review mode:

```bash
reviewbot --mode errors
```

Security-only review:

```bash
reviewbot --mode security
```

Performance-only review:

```bash
reviewbot --mode perf
```

Style and readability review:

```bash
reviewbot --mode style
```

Plain-English explanation of the diff:

```bash
reviewbot --mode explain
```

Follow-up review using repo-local history:

```bash
reviewbot --mode detail
```

## Review Sources And Modifiers

Review recent commits one commit at a time:

```bash
reviewbot --commits 3 --per-commit
```

Review the last commit as a per-commit run:

```bash
reviewbot --last --per-commit
```

Skip review if the diff touches too many files:

```bash
reviewbot --commits 3 --max-files 10
```

Review commits since a ref with a specific mode:

```bash
reviewbot --since main --mode security
```

## Common Combinations

Review the last commit with the default review lens:

```bash
reviewbot --last --mode errors
```

Explain the last commit in plain English:

```bash
reviewbot --last --mode explain
```

Run a detailed follow-up review on the last commit:

```bash
reviewbot --last --mode detail
```

Review one staged file for security issues only:

```bash
reviewbot --file path/to/file.py --mode security
```

Review one staged file for performance concerns:

```bash
reviewbot --file path/to/file.py --mode perf
```

Review the last 2 commits with a combined diff:

```bash
reviewbot --commits 2 --mode errors
```

Review the last 2 commits one-by-one:

```bash
reviewbot --commits 2 --per-commit
```

Explain all changes since a ref:

```bash
reviewbot --since HEAD~2 --mode explain
```

## Subcommand Form

ReviewBot also supports an explicit `review` subcommand:

```bash
reviewbot review
reviewbot review --last
reviewbot review --file path/to/file.py
reviewbot review --commits 3
reviewbot review --since main
reviewbot review --per-commit --last
reviewbot review --max-files 10 --commits 3
reviewbot review --mode style
```

This behaves the same as the shorter top-level command forms.

## Setup Notes

- On first run, `reviewbot` launches setup automatically if no config exists.
- `reviewbot setup` lets you switch backend, change model, or update your API key later.
- Groq and Ollama are both supported.

## Detail Mode Notes

- Detail mode uses recent review history stored in `.reviewbot/history` inside the repo.
- If no history exists yet, it falls back to `errors` mode with a warning.

## Rules

- `--since` and `--commits` cannot be used together.
- `--per-commit` requires `--since`, `--commits`, or `--last`.
- Source priority is: `--since` > `--commits` > `--last` > `--file` > staged changes.

## Help Commands

Show the main CLI help:

```bash
reviewbot --help
```

Show review subcommand help:

```bash
reviewbot review --help
```

Show setup help:

```bash
reviewbot setup --help
```
