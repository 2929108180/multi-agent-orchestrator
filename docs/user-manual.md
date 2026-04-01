# User Manual

## Overview

MAO is a local-first orchestration system for cross-vendor coding agents.

It is designed to help you:

- coordinate multiple models as a team
- review and approve changes before applying them
- manage skills and MCP servers through one registry
- resume previous sessions with memory and context

## Prerequisites

- Windows PowerShell
- Python 3.12+
- `git`
- Optional for live mode:
  - OpenAI API key
  - Anthropic API key
  - Gemini API key
  - OpenRouter or another gateway key

## Installation

```powershell
cd E:\Ai\multi-agent-orchestrator
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Basic Commands

```powershell
mao --help
mao status
mao doctor --mock
mao roadmap
```

## Mock Mode

Mock mode does not require any model API key. It is the safest way to test the workflow and approval experience.

Start chat:

```powershell
mao chat --mock
```

Example flow:

```text
做一个任务管理器
/queue
/pick 1
d
/pick 2
y
/merge
/exit
```

## Live Mode

Live mode requires a provider config and the required environment variables.

### 1. Prepare config

Start from:

- `configs/live.multi-provider.example.yaml`

Recommended local copy:

```powershell
Copy-Item configs/live.multi-provider.example.yaml configs/live.local.yaml
```

### 2. Set keys

```powershell
$env:OPENAI_API_KEY="..."
$env:GEMINI_API_KEY="..."
$env:ANTHROPIC_API_KEY="..."
$env:OPENROUTER_API_KEY="..."
```

### 3. Validate

```powershell
mao validate --config configs/live.local.yaml
```

### 4. Start live chat

```powershell
mao chat --live --config configs/live.local.yaml
```

## Chat Mode

`mao chat` supports:

- session memory (turn history + transcript)
- per-role long-lived memories (bounded summaries per worker role)
- layered context injection
- session resume
- approval queue
- merge candidate listing
- registry-backed skills and MCP access

### Common chat commands

- `/help`
- `/status`
- `/doctor`
- `/mode`
- `/history`
- `/context`
- `/skills`
- `/mcp`
- `/team auto|on|off`
- `/resume`
- `/queue`
- `/review`
- `/pick <n>`
- `/approve`
- `/reject`
- `/defer`
- `/last`
- `/merge`

### Single-model file system tools (architect)

When you are in single-model mode (either by using `/team off` or by auto-routing), the `architect` role can use the `mao_fs` MCP tools to perform file CRUD inside the project root (with guardrails).

Example (mock):

```powershell
mao chat --mock
```

```text
/team off
Create tmp/hello.txt with content: hello
Read tmp/hello.txt
Delete tmp/hello.txt
/exit
```

Notes:

- Overwrite requires `overwrite=true` and `confirm="YES"`
- Deleting a file/dir requires `confirm="DELETE"`
- Any path inside `.git/` is rejected

### Capability commands inside chat

- `/skill-import-local`
- `/mcp-import-local`
- `/register-skill <name> <path> <description>`
- `/register-mcp <name> <transport> <command|url> [args...]`
- `/grant-skill role <role> <skill>`
- `/grant-mcp role <role> <server>`
- `/bind-skill <skill> <server> <tool>`

## Session Behavior

### Per-role long-lived memories

MAO persists a small, bounded "role memory" per worker role (frontend/backend/integration/reviewer) inside the chat session JSON.

These memories are:

- **summary-only** (not a raw replay of the user transcript)
- **bounded** (kept short to avoid prompt bloat)
- injected into the corresponding worker prompts as `Role memory:` on subsequent runs


### What happens when you resume a session

Resuming a session restores:

- session id
- session turn history
- conversation context
- per-role long-lived memories (bounded summaries)
- approval queue state
- latest known run path
- saved transcript replay in the current terminal

After resuming, MAO replays the saved transcript it knows about.

You can still use:

- `/history`
- `/context`
- `/last`
- `/queue`

### Resume commands

Resume latest:

```powershell
mao chat --mock --resume-latest
```

Resume a specific session:

```powershell
mao chat --mock --session-id <session_id>
```

Resume inside chat:

```text
/resume
```

## Approval Queue

When a workflow produces reviewable changes, MAO creates approval items.

You can:

- inspect queue items
- open one item
- view a colored diff
- approve it
- reject it
- defer it and inspect another item first

This is the current review choice format:

```text
Review choice: y=yes / n=no / d=defer / b=back
```

## Merge Candidates

Approved changes can be applied into the integration worktree and registered as merge candidates.

List them:

```powershell
mao merge list
```

Current merge flow is:

`approval -> integration apply -> merge candidate`

It does **not** yet auto-merge back into the target branch.

## Capability Registry

MAO manages skills and MCP servers through its own registry:

- `runtime/registry/skills.json` (includes optional `mcp_server` / `mcp_tool` bindings)
- `runtime/registry/mcp_servers.json`

### Skill commands

```powershell
mao skills import-local
mao skills list
mao skills show mcp-builder
mao skills register demo_skill --description "demo skill" --path C:\demo\SKILL.md
mao skills grant demo_skill --role frontend

# Bind a skill to an MCP tool (Skill -> MCP indirection)
mao skills bind pdf mao_mcp mao_read_project_doc
```

### MCP commands

```powershell
mao mcp import-local
mao mcp list
mao mcp show mao_mcp
mao mcp register demo_mcp --transport streamable-http --url http://localhost:8123/mcp
mao mcp grant demo_mcp --role reviewer
```

### Policy command

```powershell
mao policy show
```

## Tool Calling (MCP + Skills)

MAO supports a cross-provider text protocol so models can request tools even when the provider adapter only returns plain text.

### TOOL_CALL protocol

When a model needs a tool, it outputs one or more exact blocks:

```text
TOOL_CALL:
TYPE: mcp|skill
NAME: <server>.<tool>      # TYPE=mcp
NAME: <skill_name>         # TYPE=skill
ARGS_JSON: <one-line json or empty>
END_TOOL_CALL
```

MAO executes the tool (if allowed for the current role/model), then appends a result block back into the model prompt:

```text
TOOL_RESULT:
TYPE: mcp|skill
NAME: ...
OK: yes|no
OUTPUT:
<tool output>
END_TOOL_RESULT
```

This repeats up to a small `max_tool_iters` limit to avoid loops.

### Skill -> MCP mapping

Skills are not executed directly. A skill must be bound to an MCP tool first:

```powershell
mao skills bind <skill> <server> <tool>
```

Or inside chat:

```text
/bind-skill <skill> <server> <tool>
```

## Direct API and Proxy Support

MAO supports both:

- direct official provider APIs
- gateways and proxies through `base_url`

Provider config can include:

- `api_key_env`
- `base_url`
- `extra_headers`

## Current Limits

Current strong areas:

- planning
- frontend/backend coordination
- review and repair
- approval queue
- capability registry
- session recovery

Still evolving:

- final merge back to a target branch
- shared-file integration actor depth
- richer UI
- natural-language capability management
