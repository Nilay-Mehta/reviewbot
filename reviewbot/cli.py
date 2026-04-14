from __future__ import annotations

import sys
import time

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from reviewbot import config, git_utils
from reviewbot.clients import LLMClient, make_client
from reviewbot.diff_parser import iter_reviewable_chunks
from reviewbot.groq_client import GroqClient, GroqConfigError
from reviewbot.models import FileReview, ReviewResult
from reviewbot.output_parser import OutputParseError, parse_review_result
from reviewbot.prompt_builder import build_user_prompt, load_system_prompt, VALID_MODES
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
DEFAULT_MODEL = "llama-3.3-70b-versatile"

app = typer.Typer(
    name="reviewbot",
    help="AI code review bot - runs LLM review over git diffs.",
    no_args_is_help=False,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
console = Console()


def _complete_with_backoff(client: LLMClient, system: str, user: str) -> str | None:
    """Call Groq synchronously with retries on 429, 5xx, and connection errors.

    Returns None only after exhausting MAX_BACKOFF_ATTEMPTS - callers should
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


def _run_review(last: bool = False, file: str | None = None, mode: str = "errors") -> None:
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

    from reviewbot.ollama_client import OllamaConfigError, OllamaConnectionError

    if mode not in VALID_MODES:
        console.print(f"[red]Unknown mode:[/red] {mode}. Valid: {sorted(VALID_MODES)}")
        raise typer.Exit(code=2)

    effective_mode = mode
    if mode == "detail":
        console.print(
            "[yellow]detail mode requires review history (Phase 3 feature). "
            "Falling back to errors mode.[/yellow]"
        )
        effective_mode = "errors"

    system_prompt = load_system_prompt(effective_mode)

    try:
        client = make_client()
    except (GroqConfigError, OllamaConfigError, OllamaConnectionError) as error:
        console.print(f"[red]config error:[/red] {escape(str(error))}")
        raise typer.Exit(code=2)

    backend_label = config.get_backend().upper()
    console.print(
        f"[bold]Reviewing {len(chunks)} file(s) via {backend_label} "
        f"({client.model}) - mode: {effective_mode}[/bold]\n"
    )

    aggregated: list[FileReview] = []
    skipped = 0

    for index, chunk in enumerate(chunks, start=1):
        console.print(
            f"[cyan][{index}/{len(chunks)}][/cyan] "
            f"reviewing [bold]{chunk.display_path}[/bold]..."
        )
        user_prompt = build_user_prompt(chunk.display_path, chunk.diff_text)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(description=f"Reviewing {chunk.display_path}...", total=None)
            raw = _complete_with_backoff(client, system_prompt, user_prompt)
        if raw is None:
            console.print("  [red]skipped[/red] (Groq errors exceeded retries)")
            skipped += 1
            if index < len(chunks):
                time.sleep(THROTTLE_SECONDS)
            continue

        def _repair(repair_prompt: str) -> str:
            repaired = _complete_with_backoff(client, system_prompt, repair_prompt)
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


def _test_groq_credentials(api_key: str, model: str) -> tuple[bool, str]:
    original_key = config.get_api_key
    original_model = config.get_model

    try:
        config.get_api_key = lambda: api_key
        config.get_model = lambda: model
        client = GroqClient(model=model)
        client.complete("You are a test. Respond in json.", '{"status": "ok"}')
        return True, "Connection successful."
    except RateLimitError:
        return True, "Connection works but you're being rate-limited, try again in a minute."
    except APIStatusError as error:
        status = getattr(error, "status_code", None)
        if status == 429:
            return True, "Connection works but you're being rate-limited, try again in a minute."
        return False, str(error)
    except Exception as error:  # pragma: no cover - network/API variability
        return False, str(error)
    finally:
        config.get_api_key = original_key
        config.get_model = original_model


def _test_ollama_connection(host: str, model: str) -> tuple[bool, str]:
    try:
        from reviewbot.ollama_client import OllamaClient

        client = OllamaClient(host=host, model=model, timeout=30.0)
        client.complete("You are a test. Respond in json.", '{"status": "ok"}')
        return True, f"Connection successful ({model} @ {host})."
    except Exception as error:
        return False, str(error)


def _setup_groq() -> None:
    console.print("[bold]Get your free API key at[/bold] https://console.groq.com/keys")

    while True:
        api_key = typer.prompt("Groq API key").strip()
        console.print(f"[dim]Press Enter to use default: {DEFAULT_MODEL}[/dim]")
        model = typer.prompt("Model", default=DEFAULT_MODEL, show_default=False).strip() or DEFAULT_MODEL

        ok, message = _test_groq_credentials(api_key, model)
        if ok:
            if "rate-limited" in message:
                console.print(f"[yellow]{escape(message)}[/yellow]")
            else:
                console.print(f"[green]OK: {escape(message)}[/green]")
            config.save_config(
                {
                    "backend": "groq",
                    "groq": {"api_key": api_key, "model": model},
                }
            )
            console.print("[green]Setup complete! Run `reviewbot` inside any git repo.[/green]")
            return

        console.print(f"[red]Connection test failed:[/red] {escape(message)}")
        if not typer.confirm("Do you want to re-enter the key?", default=True):
            raise typer.Exit(code=1)


def _setup_ollama() -> None:
    console.print("[bold]Ollama setup[/bold] - make sure the Ollama server is running locally.")
    console.print("[dim]Install from https://ollama.com if you haven't yet.[/dim]")

    default_host = "http://localhost:11434"
    host = typer.prompt("Ollama host", default=default_host).strip() or default_host

    default_model = "qwen2.5-coder:3b"
    console.print(f"[dim]Press Enter to use default: {default_model}[/dim]")
    model = (
        typer.prompt("Model", default=default_model, show_default=False).strip()
        or default_model
    )

    ok, message = _test_ollama_connection(host, model)
    if ok:
        console.print(f"[green]OK: {escape(message)}[/green]")
        config.save_config(
            {
                "backend": "ollama",
                "ollama": {"host": host, "model": model},
            }
        )
        console.print("[green]Setup complete! Run `reviewbot` inside any git repo.[/green]")
        return

    console.print(f"[red]Connection test failed:[/red] {escape(message)}")
    raise typer.Exit(code=1)


def _run_setup_wizard() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]Welcome to ReviewBot[/bold cyan]\n"
            "Let's configure your AI code review bot for first use.",
            border_style="cyan",
        )
    )

    while True:
        console.print("[bold]Choose your LLM backend:[/bold] 1) Groq (cloud, free)  2) Ollama (local)")
        choice = typer.prompt("Backend", default="1").strip()
        if choice == "1":
            _setup_groq()
            return
        if choice == "2":
            _setup_ollama()
            return
        console.print("[red]Please enter 1 or 2.[/red]")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    last: bool = typer.Option(
        False, "--last", help="Review the last commit instead of staged changes."
    ),
    file: str = typer.Option(
        None, "--file", help="Review only the staged diff for this file."
    ),
    mode: str = typer.Option(
        "errors",
        "--mode",
        help="Review mode: errors, security, perf, style, explain, detail.",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    if config.config_exists():
        _run_review(last=last, file=file, mode=mode)
        return

    _run_setup_wizard()


@app.command("review")
def review(
    last: bool = typer.Option(
        False, "--last", help="Review the last commit instead of staged changes."
    ),
    file: str = typer.Option(
        None, "--file", help="Review only the staged diff for this file."
    ),
    mode: str = typer.Option(
        "errors",
        "--mode",
        help="Review mode: errors, security, perf, style, explain, detail.",
    ),
) -> None:
    """Review staged changes (default) or the last commit."""
    _run_review(last=last, file=file, mode=mode)


@app.command("setup")
def setup() -> None:
    """Run the interactive first-run setup wizard."""
    _run_setup_wizard()


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main() or 0)
