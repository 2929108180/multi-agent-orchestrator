from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from mao_cli.config import load_config
from mao_cli.orchestrator import execute_workflow

app = typer.Typer(
    help="CLI for orchestrating cross-vendor coding agents.",
    no_args_is_help=True,
)
console = Console()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@app.command()
def doctor() -> None:
    """Show local project health information."""
    project_root = _project_root()
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


@app.command()
def goals() -> None:
    """Show the repository documents that define scope and architecture."""
    docs = [
        "docs/architecture-baseline.md",
        "docs/v1-target.md",
        "docs/progress.md",
    ]
    for path in docs:
        console.print(f"- {path}")


@app.command()
def status() -> None:
    """Show the current baseline and delivery state."""
    table = Table(title="V1 Status")
    table.add_column("Area")
    table.add_column("State")
    table.add_row("Fixed architecture", "documented")
    table.add_row("Visible goals", "documented")
    table.add_row("Config models", "implemented")
    table.add_row("Mock multi-agent flow", "implemented")
    table.add_row("Live provider helpers", "next")
    table.add_row("MCP integration", "pending")
    table.add_row("Git worktree flow", "pending")
    console.print(table)


@app.command()
def run(
    requirement: str = typer.Argument(..., help="Product or coding request."),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Directory for saved run artifacts.",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Force mock providers even if live providers are configured.",
    ),
) -> None:
    """Execute the current local orchestration workflow."""
    project_root = _project_root()
    config_path = config if config.is_absolute() else project_root / config
    loaded = load_config(config_path)
    target_dir = output_dir or (project_root / loaded.artifacts_root / "runs")
    run_dir = execute_workflow(
        requirement=requirement,
        config=loaded,
        output_dir=target_dir,
        force_mock=mock,
    )
    console.print(f"Run artifacts saved to: {run_dir}")


if __name__ == "__main__":
    app()
