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
- doctor shows configured providers and required env vars
  - use `mao doctor --config <your-live-config.yaml>` to verify live env readiness

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

# MCP import-local auto-discovers: project .mcp.json + Claude Desktop config (best-effort)
# and uses merge semantics (does not overwrite enabled/roles/models/tools)
mao mcp import-local
mao mcp list
mao mcp show mao_mcp

mao policy show
```

Expected:

- local skill import writes to registry
- local MCP import writes to registry
  - if Claude Desktop config contains a stdio MCP like `dameng_mcp`, it should be imported
- list and show commands return readable output
- policy show returns approval rules

### 5.1 Verify a stdio MCP (example: dameng_mcp) discovery + tool-call

1) Confirm Claude Desktop config contains an MCP entry:

- Windows: `%APPDATA%/Claude/claude_desktop_config.json`
- Example shape:

```json
{
  "mcpServers": {
    "dameng_mcp": {"command": "python", "args": ["-m", "dameng_mcp"], "env": {"...": "..."}}
  }
}
```

2) Import and inspect:

```powershell
mao mcp import-local
mao mcp list
mao mcp show dameng_mcp
mao mcp tools dameng_mcp
```

Expected:

- `dameng_mcp` appears in `mao mcp list`
- `mao mcp tools dameng_mcp` lists tools (if the server supports `list_tools`)

3) Verify tool calling from chat/workflow (server must be visible to the current role/model):

- To restrict visibility:

```powershell
mao mcp grant dameng_mcp --role backend
```

- Then in live/team workflow, observe `tool -> dameng_mcp.<tool>` succeeds (use an actual tool name listed above).

## 6. Single-model (architect) tool validation

### 6.1 List MCP/skills (should tool-call before answering)

```powershell
mao chat --mock
```

Inside:

```text
What MCP servers are available?
What skills are available?
/exit
```

Expected:

- tool events appear, e.g.:
  - `architect tool -> mao_mcp.mao_list_mcp_servers`
  - `architect tool -> mao_mcp.mao_list_skills`

### 6.2 Single-model file system CRUD (mao_fs)

```powershell
mao chat --mock
```

Inside:

```text
/team off
Create tmp/test.txt with content: hello
Read tmp/test.txt
List tmp directory
Delete tmp/test.txt
Delete tmp directory
/exit
```

Expected:

- `architect tool -> mao_fs.*` calls appear
- overwrite/delete requires explicit confirm fields (confirm=YES / confirm=DELETE)

## 7. Chat-Based Capability Management

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

## 8. Live Provider Preflight + Live Chat Full Run

### 8.1 Preflight (report + strict validate)

Use your real config (example: `configs/live.packyapi.yaml`).

Report mode (does not fail fast):

```powershell
mao doctor --config configs/live.packyapi.yaml
```

Strict validate (fails when any key is missing):

```powershell
mao validate --config configs/live.packyapi.yaml
```

Expected:

- if keys are missing, validation reports missing env vars and exits non-zero
- if keys are set correctly, validation prints `All configured providers are ready.`

### 8.2 Live chat start

```powershell
mao chat --live --config configs/live.packyapi.yaml
```

Expected:

- live preflight succeeds only when required keys are available
- otherwise it fails before chat starts

### 8.3 Live chat capability/registry smoke test

Inside live chat:

```text
/status
/skills
/mcp
/team auto
```

Expected:

- skills and MCP servers render in chat UI
- team mode can be queried/changed

### 8.4 Live routing spinner + single-model spinner

Inside live chat:

1) Auto routing decision (TTY should show `Deciding routing...`):

```text
Hello
```

2) Force single-model reply (TTY should show `Thinking...`):

```text
/team off
Summarize the current project status.
```

### 8.5 Live team workflow run (end-to-end)

Inside live chat:

```text
/team on
Build a small task tracker with FE dashboard and BE API.
/exit
```

Expected:

- workflow events appear for architect/frontend/backend/integration/reviewer
- run artifacts are saved
- approval queue is updated when decisions exist

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
- MAO will replay the saved session transcript on startup (a convenience replay, not your terminal scrollback)
