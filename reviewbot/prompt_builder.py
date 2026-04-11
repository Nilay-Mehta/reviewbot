from pathlib import Path

SYSTEM_PROMPT = """You are a senior software engineer performing a strict but fair code review.

You only flag real issues — never invent problems to seem useful. If a diff looks fine, return an empty comments array. A clean review is a valid and common response.

You respond with ONLY a single JSON object matching the required schema. No prose, no markdown, no code fences — just the JSON object."""


STRICT_REMINDER = """Your previous response was not valid JSON matching the required schema. Return ONLY the JSON object — no prose, no code fences, no explanation. Start with { and end with }."""


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
- The files array must contain exactly one entry — the file above.
- If the diff is fine, return a files entry with an empty comments array and a neutral summary, and "overall_verdict": "approve".
- Only flag issues you can point to specifically in the diff above.
- Line numbers must reference lines actually present in the diff — never invent them. Prefer null over guessing.
- "blocker" is reserved for genuine correctness or security bugs. Most comments should be "minor" or "nit".
- Never output anything outside the single JSON object.
"""


def build_user_prompt(filename: str, hunk: str) -> str:
    return (
        USER_TEMPLATE
        .replace("__FILENAME__", filename)
        .replace("__LANGUAGE__", detect_language(filename))
        .replace("__HUNK__", hunk)
    )


def estimate_tokens(text: str) -> int:
    """Cheap heuristic — assume ~4 characters per token. Used only for rate budgeting."""
    return max(1, len(text) // 4)
