from reviewbot.diff_parser import iter_reviewable_chunks, split_unified_diff
from reviewbot.output_parser import OutputParseError, parse_review_result


def test_split_unified_diff_breaks_into_files() -> None:
    raw = """diff --git a/foo.py b/foo.py
index 123..456 100644
--- a/foo.py
+++ b/foo.py
@@ -1 +1 @@
-print("old")
+print("new")
diff --git a/bar.py b/bar.py
new file mode 100644
index 000..789
--- /dev/null
+++ b/bar.py
@@ -0,0 +1 @@
+print("bar")
"""
    chunks = split_unified_diff(raw)

    assert len(chunks) == 2
    assert chunks[0].display_path == "foo.py"
    assert chunks[1].is_new_file is True
    assert chunks[1].display_path == "bar.py"


def test_iter_reviewable_chunks_skips_deleted_and_binary_files() -> None:
    raw = """diff --git a/old.py b/old.py
deleted file mode 100644
index 111..000 100644
--- a/old.py
+++ /dev/null
@@ -1 +0,0 @@
-print("bye")
diff --git a/image.png b/image.png
index 123..456 100644
Binary files a/image.png and b/image.png differ
diff --git a/app.py b/app.py
index 123..456 100644
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print("old")
+print("new")
"""
    chunks = list(iter_reviewable_chunks(raw))

    assert [chunk.display_path for chunk in chunks] == ["app.py"]


def test_parse_review_result_accepts_fenced_json() -> None:
    raw = """```json
{
  "files": [
    {
      "file": "app.py",
      "summary": "One issue found.",
      "comments": [
        {
          "file": "app.py",
          "line": 12,
          "severity": "major",
          "category": "bug",
          "message": "Potential crash.",
          "suggestion": "Guard the value."
        }
      ]
    }
  ],
  "overall_verdict": "request_changes",
  "overall_summary": "A major issue was found."
}
```"""
    result = parse_review_result(raw)

    assert result.overall_verdict == "request_changes"
    assert result.files[0].comments[0].severity == "major"


def test_parse_review_result_uses_single_repair_attempt() -> None:
    broken = '{"files": {"file": "app.py"}}'
    repaired = """
    {
      "files": [],
      "overall_verdict": "approve",
      "overall_summary": "Looks good."
    }
    """

    prompts: list[str] = []

    def repair(prompt: str) -> str:
        prompts.append(prompt)
        return repaired

    result = parse_review_result(broken, repair=repair)

    assert result.overall_verdict == "approve"
    assert len(prompts) == 1


def test_parse_review_result_raises_after_failed_repair() -> None:
    def repair(_: str) -> str:
        return '{"files": "still wrong"}'

    try:
        parse_review_result('{"files": "wrong"}', repair=repair)
    except OutputParseError:
        pass
    else:
        raise AssertionError("Expected OutputParseError")
