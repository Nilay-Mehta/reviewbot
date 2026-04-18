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

## Subcommand Form

ReviewBot also supports an explicit `review` subcommand:

```bash
reviewbot review
reviewbot review --last
reviewbot review --file path/to/file.py
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
