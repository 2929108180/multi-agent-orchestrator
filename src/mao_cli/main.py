from __future__ import annotations

from pathlib import Path

import typer
import json

from mao_cli.chat import ChatSession
from mao_cli.config import load_config
from mao_cli.mcp_client import (
    call_mcp_tool_sync,
    list_mcp_tools_sync,
    parse_arguments_file,
    parse_arguments_json,
)
from mao_cli.mcp_server import run_mcp_server
from mao_cli.mergeflow import list_merge_candidates
from mao_cli.registry import (
    assign_mcp_access,
    assign_skill_access,
    find_mcp_record,
    find_skill_record,
    import_local_mcp,
    import_local_skills,
    load_mcp_registry,
    load_skill_registry,
    register_mcp_server,
    register_skill,
)
from mao_cli.orchestrator import execute_workflow
from mao_cli.providers import inspect_providers
from mao_cli.security import ensure_project_path, validate_requirement
from mao_cli.sessions import export_session_markdown, load_session
from mao_cli.terminal import create_console, create_table

app = typer.Typer(
    help="CLI for orchestrating cross-vendor coding agents.",
    no_args_is_help=True,
)
console = create_console()
skills_app = typer.Typer(help="Manage skill registry entries.")
mcp_app = typer.Typer(help="Manage MCP registry entries.")
policy_app = typer.Typer(help="Inspect approval and capability policy.")
merge_app = typer.Typer(help="Inspect merge candidates.")
session_app = typer.Typer(help="Manage saved chat sessions.")
app.add_typer(skills_app, name="skills")
app.add_typer(mcp_app, name="mcp")
app.add_typer(policy_app, name="policy")
app.add_typer(merge_app, name="merge")
app.add_typer(session_app, name="session")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_config_path(project_root: Path, config: Path) -> Path:
    try:
        return ensure_project_path(project_root, config, must_exist=True, label="config")
    except FileNotFoundError as exc:
        message = (
            f"Config file not found: {config}. "
            "Use a path under the project root, for example `configs/local.example.yaml`."
        )
        raise typer.BadParameter(message) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _runtime_root(project_root: Path, config: Path | None = None) -> str:
    config_path = config or Path("configs/local.example.yaml")
    resolved = _resolve_config_path(project_root, config_path)
    return load_config(resolved).runtime_root


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
    config_path = _resolve_config_path(project_root, config)
    loaded = load_config(config_path)
    provider_health = inspect_providers(config=loaded, force_mock=mock)

    table = create_table("Environment")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Project root", str(project_root))
    table.add_row("Runtime dir", str(runtime_dir))
    table.add_row("Artifacts dir", str(artifacts_dir))
    table.add_row("Config", str(config_path))
    table.add_row("Status", "ready for local development")
    console.print(table)

    provider_table = create_table("Providers")
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
    table = create_table("V1 Status")
    table.add_column("Area")
    table.add_column("State")
    table.add_row("Fixed architecture", "documented")
    table.add_row("Visible goals", "documented")
    table.add_row("Config models", "implemented")
    table.add_row("Mock multi-agent flow", "implemented")
    table.add_row("Live provider helpers", "implemented")
    table.add_row("Live chat preflight", "implemented")
    table.add_row("MCP integration", "implemented")
    table.add_row("Git worktree flow", "implemented")
    table.add_row("Structured repair routing", "implemented")
    table.add_row("Security baseline", "implemented")
    table.add_row("Session memory", "implemented")
    table.add_row("Team mode skills", "implemented")
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
    config_path = _resolve_config_path(project_root, config)
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
    try:
        requirement = validate_requirement(requirement)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    config_path = _resolve_config_path(project_root, config)
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


@app.command()
def chat(
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
        True,
        "--mock/--live",
        help="Use mock providers by default for chat sessions.",
    ),
    with_worktrees: bool = typer.Option(
        False,
        "--with-worktrees",
        help="Create isolated git worktrees for frontend and backend outputs.",
    ),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help="Resume a specific saved chat session by id.",
    ),
    resume_latest: bool = typer.Option(
        False,
        "--resume-latest",
        help="Resume the most recently saved chat session.",
    ),
) -> None:
    """Start an interactive local chat session over the current workflow."""
    project_root = _project_root()
    config_path = _resolve_config_path(project_root, config)
    try:
        session = ChatSession(
            project_root=project_root,
            config_path=config_path,
            output_dir=output_dir,
            mock=mock,
            with_worktrees=with_worktrees,
            session_id=session_id,
            resume_latest=resume_latest,
            console=console,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    session.run()


@app.command("mcp-serve")
def mcp_serve(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        help="MCP transport: stdio or streamable-http.",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Host for streamable-http transport.",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        min=1,
        max=65535,
        help="Port for streamable-http transport.",
    ),
) -> None:
    """Run the local MCP server for project tools and workflow execution."""
    if transport not in {"stdio", "streamable-http"}:
        raise typer.BadParameter("Transport must be `stdio` or `streamable-http`.")
    run_mcp_server(transport=transport, host=host, port=port)


@skills_app.command("import-local")
def skills_import_local(
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    )
) -> None:
    """Import locally discovered skills into the MAO registry."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    target = import_local_skills(project_root, runtime_root)
    records = load_skill_registry(project_root, runtime_root)
    table = create_table("Imported Skills")
    table.add_column("Name")
    table.add_column("Source")
    table.add_column("Description")
    for record in records:
        table.add_row(record.name, record.source, record.description)
    console.print(table)
    console.print(f"registry={target}")
    console.print(f"imported={len(records)}")


@skills_app.command("list")
def skills_list(
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    )
) -> None:
    """List registered skills."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    records = load_skill_registry(project_root, runtime_root)
    table = create_table("Skill Registry")
    table.add_column("Name")
    table.add_column("Enabled")
    table.add_column("Source")
    table.add_column("Description")
    for record in records:
        table.add_row(record.name, str(record.enabled), record.source, record.description)
    console.print(table)


@skills_app.command("show")
def skills_show(
    name: str = typer.Argument(..., help="Skill name."),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """Show one registered skill."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    record = find_skill_record(project_root, runtime_root, name)
    console.print(
        "\n".join(
            [
                f"name={record.name}",
                f"enabled={record.enabled}",
                f"source={record.source}",
                f"path={record.path}",
                f"description={record.description}",
                f"roles={record.roles}",
                f"models={record.models}",
            ]
        )
    )


@skills_app.command("register")
def skills_register(
    name: str = typer.Argument(...),
    description: str = typer.Option(..., "--description"),
    path: str = typer.Option(..., "--path"),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """Register or update one skill in the registry."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    target = register_skill(project_root, runtime_root, name=name, description=description, path=path)
    console.print(f"registered={name}")
    console.print(f"registry={target}")


@skills_app.command("grant")
def skills_grant(
    name: str = typer.Argument(...),
    role: str | None = typer.Option(None, "--role"),
    model: str | None = typer.Option(None, "--model"),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """Grant a role or model access to a registered skill."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    target = assign_skill_access(project_root, runtime_root, name=name, role=role, model=model)
    console.print(f"granted={name}")
    console.print(f"registry={target}")


@mcp_app.command("import-local")
def mcp_import_local(
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    )
) -> None:
    """Import locally known MCP servers into the MAO registry."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    target = import_local_mcp(project_root, runtime_root)
    records = load_mcp_registry(project_root, runtime_root)
    table = create_table("Imported MCP Servers")
    table.add_column("Server")
    table.add_column("Transport")
    table.add_column("Source")
    table.add_column("Enabled")
    for record in records:
        table.add_row(record.name, record.transport, record.source, str(record.enabled))
    console.print(table)
    console.print(f"registry={target}")
    console.print(f"imported={len(records)}")


@mcp_app.command("list")
def mcp_list(
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    )
) -> None:
    """List registered MCP servers."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    records = load_mcp_registry(project_root, runtime_root)
    table = create_table("MCP Registry")
    table.add_column("Server")
    table.add_column("Transport")
    table.add_column("Enabled")
    table.add_column("Source")
    for record in records:
        table.add_row(record.name, record.transport, str(record.enabled), record.source)
    console.print(table)


@mcp_app.command("show")
def mcp_show(
    name: str = typer.Argument(..., help="MCP server name."),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """Show one registered MCP server."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    record = find_mcp_record(project_root, runtime_root, name)
    console.print(
        "\n".join(
            [
                f"name={record.name}",
                f"transport={record.transport}",
                f"enabled={record.enabled}",
                f"source={record.source}",
                f"command={record.command}",
                f"args={record.args}",
                f"url={record.url}",
                f"roles={record.roles}",
                f"models={record.models}",
                f"tools={len(record.tools)}",
            ]
        )
    )


@mcp_app.command("register")
def mcp_register(
    name: str = typer.Argument(...),
    transport: str = typer.Option(..., "--transport"),
    command: str = typer.Option("", "--command"),
    url: str = typer.Option("", "--url"),
    args: str = typer.Option("", "--args", help="Space-separated arguments for stdio command."),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """Register or update one MCP server in the registry."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    arg_list = [part for part in args.split(" ") if part]
    target = register_mcp_server(
        project_root,
        runtime_root,
        name=name,
        transport=transport,
        command=command,
        args=arg_list,
        url=url,
    )
    console.print(f"registered={name}")
    console.print(f"registry={target}")


@mcp_app.command("grant")
def mcp_grant(
    name: str = typer.Argument(...),
    role: str | None = typer.Option(None, "--role"),
    model: str | None = typer.Option(None, "--model"),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """Grant a role or model access to a registered MCP server."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    target = assign_mcp_access(project_root, runtime_root, name=name, role=role, model=model)
    console.print(f"granted={name}")
    console.print(f"registry={target}")


@mcp_app.command("call")
def mcp_call(
    server: str = typer.Argument(..., help="MCP server name."),
    tool: str = typer.Argument(..., help="Tool name to call."),
    args: str = typer.Option(
        "",
        "--args",
        help="Tool arguments as inline JSON string.",
    ),
    args_file: Path | None = typer.Option(
        None,
        "--args-file",
        help="Path to a JSON file containing tool arguments.",
    ),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """Call a registered MCP tool and print the result."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    record = find_mcp_record(project_root, runtime_root, server)

    if not record.enabled:
        raise typer.BadParameter(f"MCP server `{server}` is disabled in the registry.")

    if args and args_file is not None:
        raise typer.BadParameter("Use either --args or --args-file, not both.")

    arguments = None
    if args_file is not None:
        # Keep args_file inside project root for safety.
        resolved = ensure_project_path(project_root, args_file, must_exist=True, label="args_file")
        arguments = parse_arguments_file(resolved)
    elif args:
        arguments = parse_arguments_json(args)

    output = call_mcp_tool_sync(record, tool=tool, arguments=arguments)
    if output.text:
        console.print(output.text)
    elif output.structured is not None:
        console.print_json(data=output.structured)
    else:
        console.print("(no content)")


@mcp_app.command("tools")
def mcp_tools(
    server: str = typer.Argument(..., help="MCP server name."),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """List tools exposed by a registered MCP server."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    record = find_mcp_record(project_root, runtime_root, server)

    tools = list_mcp_tools_sync(record)
    table = create_table(f"MCP Tools: {record.name}")
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Schema")
    for item in tools:
        schema_text = json.dumps(item.input_schema, ensure_ascii=False) if item.input_schema else ""
        table.add_row(item.name, item.description or "", schema_text)
    console.print(table)


@policy_app.command("show")
def policy_show(
    config: Path = typer.Option(
        Path("configs/live.multi-provider.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file.",
    )
) -> None:
    """Show approval policy from config."""
    project_root = _project_root()
    config_path = _resolve_config_path(project_root, config)
    loaded = load_config(config_path)

    base = create_table("Approval")
    base.add_column("Key")
    base.add_column("Value")
    base.add_row("config", str(config_path))
    base.add_row("default_mode", loaded.approval.default_mode)
    base.add_row("shared_path_mode", loaded.approval.shared_path_mode)
    base.add_row("conflict_mode", loaded.approval.conflict_mode)
    console.print(base)

    roles = create_table("Role Overrides")
    roles.add_column("Role")
    roles.add_column("Mode")
    for role, rule in loaded.approval.role_overrides.items():
        roles.add_row(role, rule.mode)
    console.print(roles)

    providers = create_table("Provider Overrides")
    providers.add_column("Model")
    providers.add_column("Mode")
    for model, rule in loaded.approval.provider_overrides.items():
        providers.add_row(model, rule.mode)
    console.print(providers)


@merge_app.command("list")
def merge_list(
    limit: int = typer.Option(20, "--limit", min=1, max=200),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """List merge candidates stored by MAO."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    candidates = list_merge_candidates(project_root, runtime_root, limit=limit)
    table = create_table("Merge Candidates")
    table.add_column("Candidate")
    table.add_column("Run")
    table.add_column("Role")
    table.add_column("Path")
    table.add_column("Status")
    table.add_column("Shared")
    for item in candidates:
        table.add_row(
            item.candidate_id,
            item.run_id,
            item.role,
            item.path,
            item.status,
            str(item.shared_file),
        )
    console.print(table)


@session_app.command("export")
def session_export(
    session_id: str = typer.Argument(..., help="Saved session id."),
    output: Path = typer.Option(
        Path(""),
        "--output",
        "-o",
        help="Output markdown path. Defaults to runtime/sessions/<id>.md",
    ),
    config: Path = typer.Option(
        Path("configs/local.example.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config file (controls runtime_root).",
    ),
) -> None:
    """Export a saved chat session transcript as markdown."""
    project_root = _project_root()
    runtime_root = _runtime_root(project_root, config)
    session = load_session(project_root, runtime_root, session_id)
    markdown = export_session_markdown(session)

    target = output
    if not str(target):
        target = project_root / runtime_root / "sessions" / f"{session_id}.md"
    else:
        # Keep exports inside project root.
        target = ensure_project_path(project_root, target, must_exist=False, label="output")
        target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(markdown, encoding="utf-8")
    console.print(f"exported={target}")


if __name__ == "__main__":
    app()
