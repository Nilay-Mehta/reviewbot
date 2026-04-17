from importlib.resources import files
from pathlib import Path

from reviewbot.models import ReviewResult

_PROMPTS_DIR = files("reviewbot") / "prompts"
VALID_MODES = {"errors", "security", "perf", "style", "explain", "detail"}
DEFAULT_MODE = "errors"


def load_system_prompt(mode: str) -> str:
    """Load the system prompt for the given mode from reviewbot/prompts/<mode>.md."""
    if mode not in VALID_MODES:
        raise ValueError(f"Unknown mode: {mode}. Valid modes: {sorted(VALID_MODES)}")
    prompt_file = _PROMPTS_DIR / f"{mode}.md"
    return prompt_file.read_text(encoding="utf-8")


# Keep the old SYSTEM_PROMPT name for backward compat as the default
SYSTEM_PROMPT = load_system_prompt(DEFAULT_MODE)


STRICT_REMINDER = """Your previous response was not valid JSON matching the required schema. Return ONLY the JSON object - no prose, no code fences, no explanation. Start with { and end with }."""


_LANGUAGE_BY_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".jsx": "JavaScript (React)",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".h": "C/C++ header",
    ".hpp": "C++ header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Shell",
    ".bash": "Bash",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".md": "Markdown",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".xml": "XML",
    ".dockerfile": "Dockerfile",
}


def detect_language(filename: str) -> str:
    path = Path(filename)
    if path.name.lower() == "dockerfile":
        return "Dockerfile"
    return _LANGUAGE_BY_EXT.get(path.suffix.lower(), "Unknown")


USER_TEMPLATE = """Review this git diff for one file.

File: __FILENAME__
Language: __LANGUAGE__

```diff
__HUNK__
```

Return exactly one JSON object with this shape:

{
  "files": [
    {
      "file": "__FILENAME__",
      "comments": [
        {
          "file": "__FILENAME__",
          "line": <int line number that appears in the diff above, or null>,
          "severity": "blocker" | "major" | "minor" | "nit",
          "category": "bug" | "security" | "perf" | "style" | "design" | "docs",
          "message": "one or two sentence explanation",
          "suggestion": "concrete fix, or null"
        }
      ],
      "summary": "one sentence summary of this file"
    }
  ],
  "overall_verdict": "approve" | "approve_with_comments" | "request_changes",
  "overall_summary": "one sentence summary of the whole review"
}

Rules:
- The files array must contain exactly one entry - the file above.
- If the diff is fine, return a files entry with an empty comments array and a neutral summary, and "overall_verdict": "approve".
- Only flag issues you can point to specifically in the diff above.
- Line numbers must reference lines actually present in the diff above - never invent them. Prefer null over guessing.
- "blocker" is reserved for genuine correctness or security bugs. Most comments should be "minor" or "nit".
- Never output anything outside the single JSON object.
"""


def build_detail_context(previous: list[ReviewResult], max_chars: int = 2000) -> str:
    """Compress prior reviews into a prompt-friendly string."""
    lines = ["Previously flagged in this codebase:"]
    current_length = len(lines[0])

    for result in previous:
        for file_review in result.files:
            for comment in file_review.comments:
                if comment.severity not in {"blocker", "major"}:
                    continue
                location = f"{comment.file}:{comment.line}" if comment.line is not None else comment.file
                entry = f"- {location} [{comment.severity}/{comment.category}] {comment.message}"
                additional = len(entry) + 1
                if current_length + additional > max_chars:
                    rendered = "\n".join(lines)
                    if len(rendered) + 3 > max_chars:
                        return rendered[: max(0, max_chars - 3)].rstrip() + "..."
                    return rendered + "\n..."
                lines.append(entry)
                current_length += additional

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def build_user_prompt(filename: str, hunk: str, prior_context: str = "") -> str:
    rendered = (
        USER_TEMPLATE
        .replace("__FILENAME__", filename)
        .replace("__LANGUAGE__", detect_language(filename))
        .replace("__HUNK__", hunk)
    )
    if prior_context:
        return f"{prior_context}\n\n---\n\n{rendered}"
    return rendered


def estimate_tokens(text: str) -> int:
    """Cheap heuristic - assume ~4 characters per token. Used only for rate budgeting."""
    return max(1, len(text) // 4)
