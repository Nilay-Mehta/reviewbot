from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.table import Table

from reviewbot.models import FileReview, ReviewResult

SEVERITY_STYLES = {
    "blocker": "bold red",
    "major": "yellow",
    "minor": "cyan",
    "nit": "dim",
}


def render_review_report(result: ReviewResult, console: Console | None = None) -> int:
    console = console or Console()

    if not result.files:
        console.print("[green]No review comments.[/green]")
        if result.overall_summary:
            console.print(result.overall_summary)
        return 0

    for file_review in result.files:
        _render_file_review(console, file_review)

    console.print(
        f"[bold]Verdict:[/bold] {result.overall_verdict} | "
        f"[bold]Summary:[/bold] {result.overall_summary or 'No overall summary provided.'}"
    )
    return exit_code_for_result(result)


def exit_code_for_result(result: ReviewResult) -> int:
    severities = Counter(
        comment.severity
        for file_review in result.files
        for comment in file_review.comments
    )
    if severities["blocker"] or severities["major"]:
        return 1
    return 0


def _render_file_review(console: Console, file_review: FileReview) -> None:
    console.print(f"\n[bold]{file_review.file}[/bold]")
    console.print(file_review.summary)

    if not file_review.comments:
        console.print("[green]No issues found.[/green]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Severity", style="white", no_wrap=True)
    table.add_column("Category", style="white", no_wrap=True)
    table.add_column("Line", justify="right", no_wrap=True)
    table.add_column("Message")
    table.add_column("Suggestion")

    for comment in file_review.comments:
        style = SEVERITY_STYLES.get(comment.severity, "white")
        table.add_row(
            f"[{style}]{comment.severity}[/{style}]",
            comment.category,
            "-" if comment.line is None else str(comment.line),
            comment.message,
            comment.suggestion or "-",
        )

    console.print(table)
