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

- session memory
- layered context
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
- `/resume`
- `/queue`
- `/review`
- `/pick <n>`
- `/approve`
- `/reject`
- `/defer`
- `/last`
- `/merge`

### Capability commands inside chat

- `/skill-import-local`
- `/mcp-import-local`
- `/register-skill <name> <path> <description>`
- `/register-mcp <name> <transport> <command|url> [args...]`
- `/grant-skill role <role> <skill>`
- `/grant-mcp role <role> <server>`

## Session Behavior

### What happens when you resume a session

Resuming a session restores:

- session id
- session turn history
- conversation context
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

- `runtime/registry/skills.json`
- `runtime/registry/mcp_servers.json`

### Skill commands

```powershell
mao skills import-local
mao skills list
mao skills show mcp-builder
mao skills register demo_skill --description "demo skill" --path C:\demo\SKILL.md
mao skills grant demo_skill --role frontend
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
