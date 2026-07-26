from __future__ import annotations

import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from .orchestrator import Orchestrator
from .storage.meta_store import MetaStore

app = typer.Typer()
console = Console()

STORAGE_DIRNAME = ".codebase-reviewer"

_SEVERITY_STYLE = {
    "critical": "red bold",
    "warning": "yellow",
    "info": "blue",
    "suggestion": "green",
}


def _load_env(repo: Path) -> None:
    env_file = repo / ".env"
    if env_file.is_file():
        load_dotenv(env_file)


@app.command()
def index(repo: Path, force: bool = False):
    _load_env(repo)
    storage_dir = repo / STORAGE_DIRNAME
    try:
        orch = Orchestrator(repo, storage_dir)
        stats = orch.ensure_indexed(force=force)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    for error in stats.errors:
        console.print(f"[red]{error}[/red]")
    if (stats.files_indexed == 0 and stats.files_skipped == 0
            and stats.files_deleted == 0 and not stats.errors):
        console.print("Nothing to index.")
        return
    console.print(
        f"Indexed {stats.files_indexed} files, "
        f"skipped {stats.files_skipped}, deleted {stats.files_deleted}"
    )


@app.command()
def review(repo: Path, query: str, force: bool = False, stream: bool = True):
    _load_env(repo)
    storage_dir = repo / STORAGE_DIRNAME
    try:
        orch = Orchestrator(repo, storage_dir)
        if stream:
            console.print("[dim]Generating review...[/dim]")
            try:
                for chunk in orch.review_stream(query, force_index=force):
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                sys.stdout.write("\n")
                sys.stdout.flush()
            except KeyboardInterrupt:
                console.print("\n[interrupted]")
                return
        else:
            result = orch.review(query, force_index=force)
            table = Table()
            table.add_column("Severity")
            table.add_column("File")
            table.add_column("Lines")
            table.add_column("Description")
            for finding in result.findings:
                lines = (
                    f"{finding.line_range[0]}-{finding.line_range[1]}"
                    if finding.line_range is not None else ""
                )
                style = _SEVERITY_STYLE.get(finding.severity, "")
                severity = f"[{style}]{finding.severity}[/{style}]" if style else finding.severity
                table.add_row(severity, finding.file_path or "", lines, finding.description)
            console.print(table)
            console.print(result.summary)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def status(repo: Path):
    _load_env(repo)
    storage_dir = repo / STORAGE_DIRNAME
    db_path = storage_dir / "meta.db"
    if not db_path.is_file():
        console.print("Not indexed.")
        return
    meta = MetaStore(str(db_path))
    version = meta.get_version(str(repo))
    files = meta.get_indexed_files()
    console.print(f"Index version: {version}")
    console.print(f"Files indexed: {len(files)}")


if __name__ == "__main__":
    app()