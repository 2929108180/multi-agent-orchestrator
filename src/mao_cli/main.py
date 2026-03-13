from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from mao_cli.config import load_config
from mao_cli.orchestrator import execute_workflow
from mao_cli.providers import inspect_providers

app = typer.Typer(
    help="CLI for orchestrating cross-vendor coding agents.",
    no_args_is_help=True,
)
console = Console()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@app.command()
def doctor(
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file.",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Force mock mode when reporting provider readiness.",
    ),
) -> None:
    """Show local project health information."""
    project_root = _project_root()
    runtime_dir = project_root / "runtime"
    artifacts_dir = project_root / "artifacts"
    config_path = config if config.is_absolute() else project_root / config
    loaded = load_config(config_path)
    provider_health = inspect_providers(config=loaded, force_mock=mock)

    table = Table(title="Environment")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Project root", str(project_root))
    table.add_row("Runtime dir", str(runtime_dir))
    table.add_row("Artifacts dir", str(artifacts_dir))
    table.add_row("Config", str(config_path))
    table.add_row("Status", "ready for local development")
    console.print(table)

    provider_table = Table(title="Providers")
    provider_table.add_column("Role")
    provider_table.add_column("Adapter")
    provider_table.add_column("Mode")
    provider_table.add_column("Model")
    provider_table.add_column("API Env")
    provider_table.add_column("Ready")
    provider_table.add_column("Note")
    for row in provider_health:
        provider_table.add_row(
            row.role,
            row.adapter,
            row.mode,
            row.model,
            row.api_key_env or "-",
            "yes" if row.ready else "no",
            row.note,
        )
    console.print(provider_table)


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
    table.add_row("Live provider helpers", "implemented")
    table.add_row("MCP integration", "pending")
    table.add_row("Git worktree flow", "pending")
    console.print(table)


@app.command()
def validate(
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file.",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Treat all providers as mock when validating readiness.",
    ),
) -> None:
    """Validate provider configuration and environment readiness."""
    project_root = _project_root()
    config_path = config if config.is_absolute() else project_root / config
    loaded = load_config(config_path)
    rows = inspect_providers(config=loaded, force_mock=mock)
    not_ready = [row for row in rows if not row.ready]

    for row in rows:
        console.print(
            f"[{row.role}] adapter={row.adapter} model={row.model} ready={row.ready} note={row.note}"
        )

    if not_ready:
        raise typer.Exit(code=1)
    console.print("All configured providers are ready.")


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
    with_worktrees: bool = typer.Option(
        False,
        "--with-worktrees",
        help="Create isolated git worktrees for frontend and backend outputs.",
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
        repository_root=project_root,
        force_mock=mock,
        with_worktrees=with_worktrees,
    )
    console.print(f"Run artifacts saved to: {run_dir}")


if __name__ == "__main__":
    app()
