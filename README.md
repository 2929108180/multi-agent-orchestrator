# Multi-Agent Orchestrator

English | [简体中文](./README.zh-CN.md) | [한국어](./README.ko-KR.md)

MAO is a local-first orchestration system for cross-vendor coding agents.  
It is not trying to be just another single-model chat interface. The goal is to turn multiple models, skills, MCP tools, approval policies, and integration flows into one coherent AI team workflow.

## Why MAO

- Cross-vendor collaboration
  Use different vendors for planning, frontend, backend, and review instead of forcing one model to do everything.
- Local-first control
  Sessions, run artifacts, approval queues, skill registry, and MCP registry stay on your machine.
- Unified capability layer
  Skills, MCP servers, policies, approvals, and capability exposure are managed by MAO, not left to model vendors.
- Team-oriented workflow
  Models behave as coordinated team roles rather than isolated chat bots.
- Reviewable and resumable
  You can inspect diffs, defer changes, switch to another approval item, and resume the same session later.

## Core Capabilities

- Multi-agent team orchestration
  `architect / frontend / backend / reviewer`
- Layered memory
  `session memory / task memory / review memory`
- Session recovery
  `--resume-latest`, `--session-id`, and in-chat `/resume`
- Approval policy engine
  Team default, role overrides, and model overrides
- Diff-based approval queue
  `/queue`, `/pick`, `/approve`, `/reject`, `/defer`
- Integration worktree apply
  Approved changes can be written into a dedicated integration workspace
- Capability registry
  Skills and MCP are imported, registered, listed, granted, and queried through MAO
- Direct and routed providers
  Supports official APIs and `base_url`-backed gateways

## What Makes It Different

### 1. Real Team Workflow

A typical MAO run looks like this:

1. The user provides a requirement
2. `architect` builds the execution plan and shared contract
3. `frontend` and `backend` produce proposals in parallel
4. `reviewer` checks consistency and emits defects
5. Defects are routed back to the right owner
6. Approval items are queued with diffs
7. Approved items are applied to an integration worktree

### 2. Conflict Prevention

MAO does not allow workers to freely collide on the same files. It currently includes:

- `allowed_paths / restricted_paths`
- shared file detection
- conflict detection across workers
- integration-layer decisions
- policy-driven `auto / manual / reject`

### 3. Capability Ownership

Models do not “magically know” what skills or MCP servers exist. MAO controls that layer explicitly:

- local discovery
- import into registry
- registry-backed runtime visibility
- role/model access assignment

## Common Commands

```powershell
mao chat --mock
mao chat --live --config configs/live.multi-provider.example.yaml

mao skills import-local
mao skills list
mao skills show mcp-builder
mao skills register demo_skill --description "demo skill" --path C:\demo\SKILL.md
mao skills grant demo_skill --role frontend

mao mcp import-local
mao mcp list
mao mcp show mao_mcp
mao mcp register demo_mcp --transport streamable-http --url http://localhost:8123/mcp
mao mcp grant demo_mcp --role reviewer

mao policy show
mao merge list
```

## Chat Mode

`mao chat` currently supports:

- session memory and resume
- continuous context injection
- real-time workflow stage display
- skill and MCP discovery from the registry
- diff-based approval review
- integration worktree apply

Useful in-chat commands:

- `/history`
- `/context`
- `/skills`
- `/mcp`
- `/resume`
- `/queue`
- `/review`
- `/approve`
- `/reject`
- `/defer`
- `/skill-import-local`
- `/mcp-import-local`
- `/grant-skill role <role> <skill>`
- `/grant-mcp role <role> <server>`
- `/register-skill <name> <path> <description>`
- `/register-mcp <name> <transport> <command|url> [args...]`

## Capability Registry

MAO now treats its own registry as the primary runtime source:

- `runtime/registry/skills.json`
- `runtime/registry/mcp_servers.json`

Local discovery is an import source, not the final source of truth.

That means you can:

- import existing local skills and MCP configs
- manually register new capabilities
- assign access by role or by model

## Live Provider Support

MAO supports both:

- direct official APIs
- routed or proxy-based providers through `base_url`

Unified provider config can define:

- `api_key_env`
- `base_url`
- `extra_headers`
- approval policy

## Who This Is For

- Individual developers who want a real multi-model coding team
- Teams that do not want to be locked to one model vendor
- Engineering groups that need local auditability and approval control
- AI tooling builders who want unified skill, MCP, approval, and session management

## Current Product Stage

MAO has moved past the toy stage and is now in a serious trial stage.

It is already useful for:

- requirement decomposition
- architecture planning
- frontend/backend contract alignment
- review and repair loops
- approval and integration management

Still being expanded:

- finer-grained patch and merge flow
- stronger shared-file integration actor
- target-branch merge management
- richer approval UX
- more natural in-chat skill and MCP registration

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
```

## Related Docs

- [README.zh-CN.md](./README.zh-CN.md)
- [README.ko-KR.md](./README.ko-KR.md)
- [docs/user-manual.md](./docs/user-manual.md)
- [docs/test-manual.md](./docs/test-manual.md)
- [docs/architecture-baseline.md](./docs/architecture-baseline.md)
- [docs/progress.md](./docs/progress.md)
- [docs/team-mode.md](./docs/team-mode.md)
- [docs/architecture-layers.md](./docs/architecture-layers.md)
