from __future__ import annotations

import sys
import time

import typer
from rich.console import Console
from rich.markup import escape

from reviewbot import git_utils
from reviewbot.diff_parser import iter_reviewable_chunks
from reviewbot.groq_client import GroqClient, GroqConfigError
from reviewbot.models import FileReview, ReviewResult
from reviewbot.output_parser import OutputParseError, parse_review_result
from reviewbot.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from reviewbot.reporter import render_review_report

try:
    from groq import APIConnectionError, APIStatusError, RateLimitError
except ImportError:  # pragma: no cover
    RateLimitError = APIStatusError = APIConnectionError = Exception  # type: ignore

# Groq free tier: 30 RPM, 12k TPM. A 3s gap between calls caps us at 20 RPM
# which gives the TPM window plenty of room to drain between requests.
THROTTLE_SECONDS = 3
RATE_LIMIT_BACKOFF = 10
MAX_BACKOFF_ATTEMPTS = 3
CONNECTION_BACKOFF = 2

app = typer.Typer(
    name="reviewbot",
    help="AI code review bot - runs LLM review over git diffs.",
    no_args_is_help=False,
)
console = Console()


def _complete_with_backoff(client: GroqClient, system: str, user: str) -> str | None:
    """Call Groq synchronously with retries on 429, 5xx, and connection errors.

    Returns None only after exhausting MAX_BACKOFF_ATTEMPTS — callers should
    treat that as a soft failure and keep going.
    """
    for attempt in range(1, MAX_BACKOFF_ATTEMPTS + 1):
        try:
            return client.complete(system=system, user=user)
        except RateLimitError:
            console.print(
                f"[yellow]429 rate limit (attempt {attempt}/{MAX_BACKOFF_ATTEMPTS}) "
                f"- sleeping {RATE_LIMIT_BACKOFF}s...[/yellow]"
            )
            time.sleep(RATE_LIMIT_BACKOFF)
        except APIStatusError as error:
            status = getattr(error, "status_code", None)
            if status == 429:
                console.print(
                    f"[yellow]429 (attempt {attempt}/{MAX_BACKOFF_ATTEMPTS}) "
                    f"- sleeping {RATE_LIMIT_BACKOFF}s...[/yellow]"
                )
                time.sleep(RATE_LIMIT_BACKOFF)
            elif status and 500 <= status < 600:
                console.print(f"[yellow]Groq {status} - brief backoff...[/yellow]")
                time.sleep(CONNECTION_BACKOFF)
            else:
                console.print(f"[red]Groq API error:[/red] {escape(str(error))}")
                return None
        except APIConnectionError:
            console.print("[yellow]connection error - retrying...[/yellow]")
            time.sleep(CONNECTION_BACKOFF)

    console.print(f"[red]gave up after {MAX_BACKOFF_ATTEMPTS} attempts[/red]")
    return None


def _aggregate_verdict(file_reviews: list[FileReview]) -> str:
    severities = {
        comment.severity
        for file_review in file_reviews
        for comment in file_review.comments
    }
    if "blocker" in severities or "major" in severities:
        return "request_changes"
    if any(file_review.comments for file_review in file_reviews):
        return "approve_with_comments"
    return "approve"


@app.command()
def review(
    last: bool = typer.Option(
        False, "--last", help="Review the last commit instead of staged changes."
    ),
    file: str = typer.Option(
        None, "--file", help="Review only the staged diff for this file."
    ),
) -> None:
    """Review staged changes (default) or the last commit."""
    try:
        if last:
            diff = git_utils.get_last_commit_diff()
        elif file:
            diff = git_utils.get_diff_for_file(file)
        else:
            diff = git_utils.get_staged_diff()
    except git_utils.GitError as error:
        console.print(f"[red]git error:[/red] {escape(str(error))}")
        raise typer.Exit(code=2)

    if not diff.strip():
        console.print("[yellow]No changes to review.[/yellow]")
        raise typer.Exit(code=0)

    chunks = list(iter_reviewable_chunks(diff))
    if not chunks:
        console.print("[yellow]No reviewable text diffs found.[/yellow]")
        raise typer.Exit(code=0)

    try:
        client = GroqClient()
    except GroqConfigError as error:
        console.print(f"[red]config error:[/red] {escape(str(error))}")
        raise typer.Exit(code=2)

    console.print(
        f"[bold]Reviewing {len(chunks)} file(s) via Groq "
        f"({client.model})[/bold]\n"
    )

    aggregated: list[FileReview] = []
    skipped = 0

    for index, chunk in enumerate(chunks, start=1):
        console.print(
            f"[cyan][{index}/{len(chunks)}][/cyan] "
            f"reviewing [bold]{chunk.display_path}[/bold]..."
        )
        user_prompt = build_user_prompt(chunk.display_path, chunk.diff_text)

        raw = _complete_with_backoff(client, SYSTEM_PROMPT, user_prompt)
        if raw is None:
            console.print("  [red]skipped[/red] (Groq errors exceeded retries)")
            skipped += 1
            if index < len(chunks):
                time.sleep(THROTTLE_SECONDS)
            continue

        def _repair(repair_prompt: str) -> str:
            repaired = _complete_with_backoff(client, SYSTEM_PROMPT, repair_prompt)
            return repaired or "{}"

        try:
            chunk_result = parse_review_result(raw, repair=_repair)
        except OutputParseError as error:
            console.print(f"  [red]parse error:[/red] {escape(str(error))}")
            skipped += 1
            if index < len(chunks):
                time.sleep(THROTTLE_SECONDS)
            continue

        aggregated.extend(chunk_result.files)

        # Throttle between chunks to stay well under 30 RPM and give the
        # 12k TPM sliding window time to drain. Skip the wait after the last chunk.
        if index < len(chunks):
            time.sleep(THROTTLE_SECONDS)

    if not aggregated:
        console.print("\n[red]No files were successfully reviewed.[/red]")
        raise typer.Exit(code=2)

    summary_parts = [f"Reviewed {len(aggregated)} file(s)"]
    if skipped:
        summary_parts.append(f"{skipped} skipped")
    final = ReviewResult(
        files=aggregated,
        overall_verdict=_aggregate_verdict(aggregated),
        overall_summary=", ".join(summary_parts) + ".",
    )

    console.print()
    exit_code = render_review_report(final, console)
    raise typer.Exit(code=exit_code)


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main() or 0)
