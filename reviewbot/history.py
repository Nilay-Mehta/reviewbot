from __future__ import annotations

import hashlib
from pathlib import Path

from rich import print as rich_print

from reviewbot.models import ReviewResult

HISTORY_DIRNAME = ".reviewbot/history"
MAX_ENTRIES = 30


def history_dir(repo_root: Path) -> Path:
    return repo_root / HISTORY_DIRNAME


def diff_key(diff_text: str) -> str:
    return hashlib.sha256(diff_text.encode()).hexdigest()[:16]


def save_review(repo_root: Path, diff_text: str, result: ReviewResult) -> Path:
    target_dir = history_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{diff_key(diff_text)}.json"
    target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    _rotate(repo_root)
    return target


def load_recent(repo_root: Path, limit: int = 5) -> list[ReviewResult]:
    entries: list[ReviewResult] = []
    target_dir = history_dir(repo_root)
    if not target_dir.exists():
        return entries

    files = sorted(target_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files:
        if len(entries) >= limit:
            break
        try:
            entries.append(ReviewResult.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:
            rich_print(f"[dim]history: skipped corrupt entry {path.name}[/dim]")
            continue
    return entries


def _rotate(repo_root: Path, max_entries: int = MAX_ENTRIES) -> None:
    target_dir = history_dir(repo_root)
    if not target_dir.exists():
        return

    files = sorted(target_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
    while len(files) > max_entries:
        oldest = files.pop(0)
        try:
            oldest.unlink()
        except FileNotFoundError:
            continue
