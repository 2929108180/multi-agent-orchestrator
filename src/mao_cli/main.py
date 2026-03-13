from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    help="CLI for orchestrating cross-vendor coding agents.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def doctor() -> None:
    """Show local project health information."""
    project_root = Path(__file__).resolve().parents[2]
    runtime_dir = project_root / "runtime"
    artifacts_dir = project_root / "artifacts"

    table = Table(title="Environment")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Project root", str(project_root))
    table.add_row("Runtime dir", str(runtime_dir))
    table.add_row("Artifacts dir", str(artifacts_dir))
    table.add_row("Status", "ready for local development")
    console.print(table)


@app.command()
def roadmap() -> None:
    """Show the initial delivery sequence."""
    steps = [
        "v0.1: CLI skeleton and local storage",
        "v0.2: planner and task contract generation",
        "v0.3: provider gateway and worker execution",
        "v0.4: review loop and repair protocol",
        "v0.5: git integration and reproducible runs",
    ]
    for step in steps:
        console.print(f"- {step}")


if __name__ == "__main__":
    app()
