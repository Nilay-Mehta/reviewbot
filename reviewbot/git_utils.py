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


def get_commits_diff(n: int) -> str:
    """Return combined diff of the last N commits vs HEAD~N."""
    try:
        return _run(["diff", f"HEAD~{n}", "HEAD", "--no-color"])
    except GitError:
        # N exceeds total commits — diff from root (empty tree)
        return _run(["diff", "4b825dc642cb6eb9a060e54bf899d69f82cf7137", "HEAD", "--no-color"])


def get_since_diff(ref: str) -> str:
    """Return combined diff from ref to HEAD."""
    return _run(["diff", f"{ref}...HEAD", "--no-color"])


def get_commit_list(n: int) -> list[str]:
    """Return list of last N commit SHAs, newest first."""
    output = _run(["log", f"-{n}", "--format=%H"])
    return [sha.strip() for sha in output.strip().splitlines() if sha.strip()]


def get_since_commit_list(ref: str) -> list[str]:
    """Return list of commit SHAs from ref to HEAD, newest first."""
    output = _run(["log", f"{ref}...HEAD", "--format=%H"])
    return [sha.strip() for sha in output.strip().splitlines() if sha.strip()]


def get_single_commit_diff(sha: str) -> str:
    """Return the diff for a single commit (handles initial commit)."""
    try:
        return _run(["diff", f"{sha}~1", sha, "--no-color"])
    except GitError:
        # Initial commit has no parent — diff against empty tree
        return _run(["diff", "4b825dc642cb6eb9a060e54bf899d69f82cf7137", sha, "--no-color"])


def get_diff_for_file(path: str) -> str:
    """Return the staged diff for a single file."""
    return _run(["diff", "--cached", "--no-color", "--", path])


def get_repo_root() -> Path:
    """Return the root directory of the current git repository."""
    return Path(_run(["rev-parse", "--show-toplevel"]).strip())
