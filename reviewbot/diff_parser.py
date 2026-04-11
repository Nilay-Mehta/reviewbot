from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DiffFileChunk:
    old_path: str
    new_path: str
    diff_text: str
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_binary: bool = False

    @property
    def display_path(self) -> str:
        if self.new_path != "/dev/null":
            return self.new_path
        return self.old_path

    @property
    def is_reviewable(self) -> bool:
        return bool(self.diff_text.strip()) and not self.is_deleted_file and not self.is_binary


def split_unified_diff(raw_diff: str) -> list[DiffFileChunk]:
    """Split a unified git diff into one chunk per file."""
    if not raw_diff.strip():
        return []

    chunks: list[DiffFileChunk] = []
    current_lines: list[str] = []

    for line in raw_diff.splitlines():
        if line.startswith("diff --git "):
            if current_lines:
                chunks.append(_parse_chunk(current_lines))
            current_lines = [line]
            continue

        if current_lines:
            current_lines.append(line)

    if current_lines:
        chunks.append(_parse_chunk(current_lines))

    return chunks


def iter_reviewable_chunks(raw_diff: str) -> Iterable[DiffFileChunk]:
    for chunk in split_unified_diff(raw_diff):
        if chunk.is_reviewable:
            yield chunk


def _parse_chunk(lines: list[str]) -> DiffFileChunk:
    header = lines[0]
    old_path, new_path = _parse_diff_git_header(header)
    is_new_file = False
    is_deleted_file = False
    is_binary = False

    for line in lines[1:]:
        if line.startswith("new file mode "):
            is_new_file = True
        elif line.startswith("deleted file mode "):
            is_deleted_file = True
        elif line.startswith("--- "):
            old_path = _strip_prefix(line[4:])
            if old_path == "/dev/null":
                is_new_file = True
        elif line.startswith("+++ "):
            new_path = _strip_prefix(line[4:])
            if new_path == "/dev/null":
                is_deleted_file = True
        elif line.startswith("Binary files ") or line == "GIT binary patch":
            is_binary = True

    return DiffFileChunk(
        old_path=old_path,
        new_path=new_path,
        diff_text="\n".join(lines).strip(),
        is_new_file=is_new_file,
        is_deleted_file=is_deleted_file,
        is_binary=is_binary,
    )


def _parse_diff_git_header(header_line: str) -> tuple[str, str]:
    parts = header_line.split()
    if len(parts) < 4:
        return "", ""

    old_path = _strip_prefix(parts[2])
    new_path = _strip_prefix(parts[3])
    return old_path, new_path


def _strip_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path
