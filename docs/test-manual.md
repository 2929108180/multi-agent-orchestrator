# Test Manual

English | [简体中文](./test-manual.zh-CN.md) | [한국어](./test-manual.ko-KR.md)

## Goal

This manual is for validating the full MAO workflow from basic health checks to chat, approvals, capability registry, and live-mode preflight.

## Test Order

Run tests in this order:

1. basic environment
2. mock workflow
3. session memory
4. approval queue
5. registry management
6. merge candidates
7. live provider preflight

## 1. Basic Environment

```powershell
cd E:\Ai\multi-agent-orchestrator
mao --help
mao status
mao doctor --mock
```

Expected:

- commands render successfully
- status shows implemented core areas
- doctor shows mock providers as ready

## 2. Mock Workflow

```powershell
mao chat --mock
```

Inside chat:

```text
做一个带任务列表和状态筛选的任务管理器
/exit
```

Expected:

- workflow stage messages appear
- a run directory is created
- a summary is shown
- approval queue count is shown

## 3. Session Memory

First session:

```powershell
mao chat --mock
```

Inside:

```text
做一个任务管理器
/exit
```

Resume latest:

```powershell
mao chat --mock --resume-latest
```

Inside:

```text
/history
/context
/last
/exit
```

Expected:

- history shows at least one turn
- context shows recent summarized memory
- last shows the latest run path

## 4. Approval Queue

```powershell
mao chat --mock
```

Inside:

```text
做一个任务管理器
/queue
/pick 1
d
/queue
/pick 2
y
/merge
/exit
```

Expected:

- queue displays pending approval items
- diff is shown with `+` and `-`
- deferred item stays in queue
- approved item is applied to integration worktree
- merge candidates become visible

## 5. Registry Management

```powershell
mao skills import-local
mao skills list
mao skills show mcp-builder

mao mcp import-local
mao mcp list
mao mcp show mao_mcp

mao policy show
```

Expected:

- local skill import writes to registry
- local MCP import writes to registry
- list and show commands return readable output
- policy show returns approval rules

## 6. Chat-Based Capability Management

```powershell
mao chat --mock
```

Inside:

```text
/skill-import-local
/skills
/register-skill demo_skill C:\demo\SKILL.md demo skill description
/grant-skill role frontend demo_skill
/mcp-import-local
/mcp
/register-mcp demo_http streamable-http http://localhost:8123/mcp
/grant-mcp role reviewer demo_http
/exit
```

Expected:

- import confirms registry updates
- skill list shows registered entries
- MCP list shows registered servers
- grant commands update registry paths

## 7. Merge Candidate Listing

After approving at least one item:

```powershell
mao merge list
```

Expected:

- merge candidates are listed
- status and shared flags are visible

## 8. Live Provider Preflight

Prepare a real config or use the example:

```powershell
mao validate --config configs/live.multi-provider.example.yaml
```

Expected:

- if keys are missing, validation reports missing env vars
- if keys are set correctly, validation passes

Then:

```powershell
mao chat --live --config configs/live.multi-provider.example.yaml
```

Expected:

- live preflight succeeds only when required keys are available
- otherwise it fails before chat starts

## 9. Full Regression

```powershell
pytest
```

Expected:

- all tests pass

## Troubleshooting Checklist

If something fails, collect:

- the exact command you ran
- the terminal output
- the latest run directory
- `run.json`
- `summary.md`
- `integration.json`
- `integration.md`

If session restore feels wrong, also check:

- `/history`
- `/context`
- `/queue`

Remember:

- resuming a session restores state
- it does not replay the old terminal transcript automatically
