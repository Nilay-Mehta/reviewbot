from pathlib import Path
import subprocess


class GitError(RuntimeError):
    pass


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise GitError("git is not installed or not on PATH") from e
    except subprocess.CalledProcessError as e:
        raise GitError(f"git {' '.join(args)} failed: {e.stderr.strip()}") from e
    return result.stdout


def get_staged_diff() -> str:
    """Return the unified diff for staged changes (git diff --cached)."""
    return _run(["diff", "--cached", "--no-color"])


def get_last_commit_diff() -> str:
    """Return the unified diff for the most recent commit."""
    return _run(["diff", "--no-color", "HEAD~1", "HEAD"])


def get_diff_for_file(path: str) -> str:
    """Return the staged diff for a single file."""
    return _run(["diff", "--cached", "--no-color", "--", path])


def get_repo_root() -> Path:
    """Return the root directory of the current git repository."""
    return Path(_run(["rev-parse", "--show-toplevel"]).strip())
