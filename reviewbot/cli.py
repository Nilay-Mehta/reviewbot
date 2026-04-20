from __future__ import annotations

import sys
import time

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from reviewbot import config, git_utils, history, gitignore
from reviewbot.clients import LLMClient, make_client
from reviewbot.diff_parser import DiffFileChunk, iter_reviewable_chunks
from reviewbot.gemini_client import GeminiConfigError
from reviewbot.groq_client import GroqClient, GroqConfigError
from reviewbot.models import FileReview, ReviewResult
from reviewbot.output_parser import OutputParseError, parse_review_result
from reviewbot.prompt_builder import (
    build_detail_context,
    build_user_prompt,
    load_system_prompt,
    VALID_MODES,
)
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


def _supports_unicode_output() -> bool:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in encoding


def _complete_with_backoff(client: LLMClient, system: str, user: str) -> str | None:
    """Call Groq synchronously with retries on 429, 5xx, and connection errors.

    Returns None only after exhausting MAX_BACKOFF_ATTEMPTS - callers should
    treat that as a soft failure and keep going.
    """
    from reviewbot.ollama_client import OllamaConnectionError
    from reviewbot.gemini_client import GeminiConnectionError

    for attempt in range(1, MAX_BACKOFF_ATTEMPTS + 1):
        try:
            return client.complete(system=system, user=user)
        except OllamaConnectionError as error:
            console.print(
                f"[red]Ollama not reachable:[/red] {escape(str(error))}\n"
                "[yellow]Install Ollama from https://ollama.com or switch backend: "
                "reviewbot switch[/yellow]"
            )
            return None
        except GeminiConnectionError as error:
            console.print(
                f"[red]Gemini error:[/red] {escape(str(error))}\n"
                "[yellow]Check your API key or switch backend: reviewbot switch[/yellow]"
            )
            return None
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


def _review_chunks(
    chunks: list[DiffFileChunk],
    client: LLMClient,
    system_prompt: str,
    effective_mode: str,
    detail_context: str,
) -> tuple[list[FileReview], int]:
    """Review a list of chunks, return (file_reviews, skipped_count)."""
    aggregated: list[FileReview] = []
    skipped = 0

    for index, chunk in enumerate(chunks, start=1):
        console.print(
            f"[cyan][{index}/{len(chunks)}][/cyan] "
            f"reviewing [bold]{chunk.display_path}[/bold]..."
        )
        user_prompt = build_user_prompt(
            chunk.display_path,
            chunk.diff_text,
            prior_context=detail_context if effective_mode == "detail" else "",
        )

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

    return aggregated, skipped


def _run_review(
    last: bool = False,
    file: str | None = None,
    mode: str = "errors",
    commits: int | None = None,
    since: str | None = None,
    per_commit: bool = False,
    max_files: int | None = None,
    model: str | None = None,
) -> None:
    repo_root = None
    try:
        repo_root = git_utils.get_repo_root()
        try:
            gitignore.ensure_reviewbot_ignored(repo_root)
        except Exception as error:
            console.print(f"[dim]history: gitignore update failed ({escape(str(error))})[/dim]")
    except git_utils.GitError:
        repo_root = None

    source_flags = sum(bool(x) for x in [since, commits, last, file])
    if source_flags > 1:
        console.print("[red]Use only one of --since, --commits, --last, or --file.[/red]")
        raise typer.Exit(code=2)

    if per_commit and not (since or commits or last):
        console.print("[red]--per-commit requires --since, --commits, or --last.[/red]")
        raise typer.Exit(code=2)

    try:
        if since:
            diff = git_utils.get_since_diff(since)
        elif commits:
            diff = git_utils.get_commits_diff(commits)
        elif last:
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

    if max_files and len(chunks) > max_files:
        console.print(
            f"[yellow]Diff touches {len(chunks)} file(s), exceeds --max-files {max_files}. "
            f"Skipping review.[/yellow]"
        )
        raise typer.Exit(code=0)

    from reviewbot.ollama_client import OllamaConfigError, OllamaConnectionError

    if mode not in VALID_MODES:
        console.print(f"[red]Unknown mode:[/red] {mode}. Valid: {sorted(VALID_MODES)}")
        raise typer.Exit(code=2)

    effective_mode = mode
    detail_context = ""
    if mode == "detail":
        try:
            if repo_root is None:
                repo_root = git_utils.get_repo_root()
            previous = history.load_recent(repo_root, limit=5)
        except Exception as error:
            console.print(f"[dim]history: load failed ({escape(str(error))})[/dim]")
            previous = []

        if not previous:
            console.print("[yellow]No review history yet - running detail mode as errors.[/yellow]")
            effective_mode = "errors"
        else:
            detail_context = build_detail_context(previous)
            console.print(f"[dim]detail mode: injecting {len(previous)} prior review(s) as context[/dim]")

    system_prompt = load_system_prompt(effective_mode)

    try:
        client = make_client(model_override=model)
    except (GroqConfigError, OllamaConfigError, OllamaConnectionError, GeminiConfigError) as error:
        console.print(f"[red]config error:[/red] {escape(str(error))}")
        raise typer.Exit(code=2)

    backend_label = config.get_backend().upper()
    if since:
        source = f"since {since}"
    elif commits:
        source = f"last {commits} commit(s)"
    elif last:
        source = "last commit"
    elif file:
        source = f"file {file}"
    else:
        source = "staged changes"

    if per_commit:
        if since:
            shas = git_utils.get_since_commit_list(since)
        elif commits:
            shas = git_utils.get_commit_list(commits)
        elif last:
            shas = git_utils.get_commit_list(1)
        else:
            shas = []

        if not shas:
            console.print("[yellow]No commits found to review.[/yellow]")
            raise typer.Exit(code=0)

        console.print(
            f"[bold]Reviewing {len(shas)} commit(s) via {backend_label} "
            f"({client.model}) - {source} (per-commit) - mode: {effective_mode}[/bold]\n"
        )

        all_aggregated: list[FileReview] = []
        total_skipped = 0

        for commit_idx, sha in enumerate(reversed(shas), start=1):
            short = sha[:8]
            if _supports_unicode_output():
                header = f"━━━ Commit {commit_idx}/{len(shas)}: {short} ━━━"
            else:
                header = f"--- Commit {commit_idx}/{len(shas)}: {short} ---"
            console.print(f"\n[bold cyan]{header}[/bold cyan]")
            try:
                commit_diff = git_utils.get_single_commit_diff(sha)
            except git_utils.GitError as error:
                console.print(f"[red]git error for {short}:[/red] {escape(str(error))}")
                total_skipped += 1
                continue

            if not commit_diff.strip():
                console.print(f"[yellow]{short}: empty diff, skipping.[/yellow]")
                continue

            commit_chunks = list(iter_reviewable_chunks(commit_diff))
            if not commit_chunks:
                console.print(f"[yellow]{short}: no reviewable chunks.[/yellow]")
                continue

            if max_files and len(commit_chunks) > max_files:
                console.print(f"[yellow]{short}: {len(commit_chunks)} files exceeds --max-files, skipping.[/yellow]")
                total_skipped += 1
                continue

            chunk_results, chunk_skipped = _review_chunks(
                commit_chunks, client, system_prompt, effective_mode, detail_context
            )
            all_aggregated.extend(chunk_results)
            total_skipped += chunk_skipped

        if not all_aggregated:
            console.print("\n[red]No files were successfully reviewed.[/red]")
            raise typer.Exit(code=2)

        summary_parts = [f"Reviewed {len(all_aggregated)} file(s) across {len(shas)} commit(s)"]
        if total_skipped:
            summary_parts.append(f"{total_skipped} skipped")
        final = ReviewResult(
            files=all_aggregated,
            overall_verdict=_aggregate_verdict(all_aggregated),
            overall_summary=", ".join(summary_parts) + ".",
        )
    else:
        console.print(
            f"[bold]Reviewing {len(chunks)} file(s) via {backend_label} "
            f"({client.model}) - {source} - mode: {effective_mode}[/bold]\n"
        )

        aggregated, skipped = _review_chunks(
            chunks, client, system_prompt, effective_mode, detail_context
        )

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

    try:
        if repo_root is None:
            repo_root = git_utils.get_repo_root()
        history.save_review(repo_root, diff, final)
    except Exception as error:
        console.print(f"[dim]history: save failed ({escape(str(error))})[/dim]")

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


def _test_gemini_connection(api_key: str, model: str) -> tuple[bool, str]:
    try:
        from reviewbot.gemini_client import GeminiClient

        original_key = config.get_gemini_api_key
        original_model = config.get_gemini_model
        try:
            config.get_gemini_api_key = lambda: api_key
            config.get_gemini_model = lambda: model
            client = GeminiClient(model=model)
            client.complete("You are a test. Respond in json.", '{"status": "ok"}')
            return True, f"Connection successful ({model})."
        finally:
            config.get_gemini_api_key = original_key
            config.get_gemini_model = original_model
    except Exception as error:
        return False, str(error)


def _setup_gemini() -> None:
    console.print("[bold]Get your free API key at[/bold] https://aistudio.google.com/apikey")

    while True:
        api_key = typer.prompt("Gemini API key").strip()
        default_model = "gemini-2.0-flash"
        console.print(f"[dim]Press Enter to use default: {default_model}[/dim]")
        model = typer.prompt("Model", default=default_model, show_default=False).strip() or default_model

        ok, message = _test_gemini_connection(api_key, model)
        if ok:
            console.print(f"[green]OK: {escape(message)}[/green]")
            config.save_config(
                {
                    "backend": "gemini",
                    "gemini": {"api_key": api_key, "model": model},
                }
            )
            console.print("[green]Setup complete! Run `reviewbot` inside any git repo.[/green]")
            return

        console.print(f"[red]Connection test failed:[/red] {escape(message)}")
        if not typer.confirm("Do you want to re-enter the key?", default=True):
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
        console.print("[bold]Choose your LLM backend:[/bold] 1) Groq (cloud, free)  2) Ollama (local)  3) Gemini (cloud, free)")
        choice = typer.prompt("Backend", default="1").strip()
        if choice == "1":
            _setup_groq()
            return
        if choice == "2":
            _setup_ollama()
            return
        if choice == "3":
            _setup_gemini()
            return
        console.print("[red]Please enter 1, 2, or 3.[/red]")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    last: bool = typer.Option(
        False, "--last", help="Review the last commit instead of staged changes."
    ),
    file: str = typer.Option(
        None, "--file", help="Review only the staged diff for this file."
    ),
    commits: int = typer.Option(
        None, "--commits", "-n",
        help="Review the last N commits combined (default: combined diff).",
    ),
    since: str = typer.Option(
        None, "--since",
        help="Review all commits since this ref (branch, tag, or SHA).",
    ),
    per_commit: bool = typer.Option(
        False, "--per-commit",
        help="Review each commit separately instead of combining into one diff.",
    ),
    max_files: int = typer.Option(
        None, "--max-files",
        help="Skip review if diff touches more than this many files.",
    ),
    mode: str = typer.Option(
        "errors",
        "--mode",
        help="Review mode: errors, security, perf, style, explain, detail.",
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Override the LLM model for this run (e.g. deepseek-r1-distill-llama-70b).",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    if config.config_exists():
        _run_review(
            last=last,
            file=file,
            mode=mode,
            commits=commits,
            since=since,
            per_commit=per_commit,
            max_files=max_files,
            model=model,
        )
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
    commits: int = typer.Option(
        None, "--commits", "-n",
        help="Review the last N commits combined (default: combined diff).",
    ),
    since: str = typer.Option(
        None, "--since",
        help="Review all commits since this ref (branch, tag, or SHA).",
    ),
    per_commit: bool = typer.Option(
        False, "--per-commit",
        help="Review each commit separately instead of combining into one diff.",
    ),
    max_files: int = typer.Option(
        None, "--max-files",
        help="Skip review if diff touches more than this many files.",
    ),
    mode: str = typer.Option(
        "errors",
        "--mode",
        help="Review mode: errors, security, perf, style, explain, detail.",
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Override the LLM model for this run (e.g. deepseek-r1-distill-llama-70b).",
    ),
) -> None:
    """Review staged changes (default) or the last commit."""
    _run_review(
        last=last,
        file=file,
        mode=mode,
        commits=commits,
        since=since,
        per_commit=per_commit,
        max_files=max_files,
        model=model,
    )


@app.command("setup")
def setup() -> None:
    """Run the interactive first-run setup wizard."""
    _run_setup_wizard()


@app.command("switch")
def switch() -> None:
    """Switch backend or model without re-entering credentials."""
    cfg = config.load_config()
    current_backend = config.get_backend()

    console.print(f"[bold]Current backend:[/bold] {current_backend}")
    if current_backend == "groq":
        console.print(f"[bold]Current model:[/bold] {config.get_model()}")
    elif current_backend == "gemini":
        console.print(f"[bold]Current model:[/bold] {config.get_gemini_model()}")
    else:
        console.print(f"[bold]Current model:[/bold] {config.get_ollama_model()}")

    console.print("\n[bold]Quick switch options:[/bold]")
    console.print("  1) Groq - llama-3.3-70b-versatile (recommended)")
    console.print("  2) Groq - qwen/qwen3-32b")
    console.print("  3) Groq - meta-llama/llama-4-scout-17b-16e-instruct")
    console.print("  4) Gemini - gemini-2.0-flash")
    console.print("  5) Gemini - gemini-2.5-flash")
    console.print("  6) Ollama - custom model")
    console.print("  7) Groq - custom model")
    console.print("  8) Gemini - custom model")

    choice = typer.prompt("Choice").strip()

    presets = {
        "1": ("groq", "llama-3.3-70b-versatile"),
        "2": ("groq", "qwen/qwen3-32b"),
        "3": ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
        "4": ("gemini", "gemini-2.0-flash"),
        "5": ("gemini", "gemini-2.5-flash"),
    }

    if choice in presets:
        backend, model = presets[choice]
    elif choice == "6":
        backend = "ollama"
        model = typer.prompt("Ollama model name").strip()
    elif choice == "7":
        backend = "groq"
        model = typer.prompt("Groq model name").strip()
    elif choice == "8":
        backend = "gemini"
        model = typer.prompt("Gemini model name").strip()
    else:
        console.print("[red]Invalid choice.[/red]")
        raise typer.Exit(code=1)

    # Preserve existing credentials, just update backend + model
    if backend == "groq":
        groq_cfg = cfg.get("groq", {}) if isinstance(cfg.get("groq"), dict) else {}
        groq_cfg["model"] = model
        if not groq_cfg.get("api_key"):
            console.print("[yellow]No Groq API key found. Run `reviewbot setup` first.[/yellow]")
            raise typer.Exit(code=1)
        cfg["backend"] = "groq"
        cfg["groq"] = groq_cfg
    elif backend == "gemini":
        gemini_cfg = cfg.get("gemini", {}) if isinstance(cfg.get("gemini"), dict) else {}
        gemini_cfg["model"] = model
        if not gemini_cfg.get("api_key"):
            console.print("[yellow]No Gemini API key found. Run `reviewbot setup` first.[/yellow]")
            raise typer.Exit(code=1)
        cfg["backend"] = "gemini"
        cfg["gemini"] = gemini_cfg
    else:
        ollama_cfg = cfg.get("ollama", {}) if isinstance(cfg.get("ollama"), dict) else {}
        ollama_cfg["model"] = model
        if not ollama_cfg.get("host"):
            ollama_cfg["host"] = "http://localhost:11434"
        cfg["backend"] = "ollama"
        cfg["ollama"] = ollama_cfg

    config.save_config(cfg)
    console.print(f"[green]Switched to {backend.upper()} ({model}).[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main() or 0)
