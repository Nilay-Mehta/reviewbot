from __future__ import annotations

from pathlib import Path


def ensure_reviewbot_ignored(repo_root: Path) -> None:
    gitignore_path = repo_root / ".gitignore"
    ignore_line = ".reviewbot/"

    if not gitignore_path.exists():
        gitignore_path.write_text(f"{ignore_line}\n", encoding="utf-8")
        return

    existing = gitignore_path.read_text(encoding="utf-8")
    normalized = {line.strip() for line in existing.splitlines()}
    if ignore_line in normalized or ".reviewbot" in normalized:
        return

    suffix = "" if existing.endswith("\n") or not existing else "\n"
    gitignore_path.write_text(f"{existing}{suffix}{ignore_line}\n", encoding="utf-8")
