# 使用手册

[English](./user-manual.md) | 简体中文

## 概览

MAO 是一个本地优先的跨厂商编码代理编排系统。

它帮助你：

- 把多个模型组织成一个团队
- 在应用修改前先审查和审批
- 用统一 registry 管理 skill 和 MCP
- 恢复之前的会话、上下文和审批状态

## 环境要求

- Windows PowerShell
- Python 3.12+
- `git`
- 如果使用 live：
  - OpenAI key
  - Anthropic key
  - Gemini key
  - OpenRouter 或其他网关 key

## 安装

```powershell
cd E:\Ai\multi-agent-orchestrator
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## 常用命令

```powershell
mao --help
mao status
mao doctor --mock
mao roadmap
```

## Mock 模式

mock 模式不需要任何 API key，适合先验证 workflow 和审批体验。

启动：

```powershell
mao chat --mock
```

示例：

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

## Live 模式

live 模式需要 provider 配置和环境变量。

### 1. 准备配置

从这个文件开始：

- `configs/live.multi-provider.example.yaml`

复制一份：

```powershell
Copy-Item configs/live.multi-provider.example.yaml configs/live.local.yaml
```

### 2. 设置 key

```powershell
$env:OPENAI_API_KEY="..."
$env:GEMINI_API_KEY="..."
$env:ANTHROPIC_API_KEY="..."
$env:OPENROUTER_API_KEY="..."
```

### 3. 预检

```powershell
mao validate --config configs/live.local.yaml
```

### 4. 启动

```powershell
mao chat --live --config configs/live.local.yaml
```

## Chat 模式

当前支持：

- session memory
- 分层上下文
- session resume
- transcript 回放
- 审批队列
- merge candidate
- registry 驱动的 skill / MCP 能力

### 常用聊天命令

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

### 聊天中管理能力

- `/skill-import-local`
- `/mcp-import-local`
- `/register-skill <name> <path> <description>`
- `/register-mcp <name> <transport> <command|url> [args...]`
- `/grant-skill role <role> <skill>`
- `/grant-mcp role <role> <server>`

## 会话恢复

恢复时会带回：

- session id
- session history
- context
- queue
- last run
- 已保存 transcript 的回放

恢复最近会话：

```powershell
mao chat --mock --resume-latest
```

恢复指定会话：

```powershell
mao chat --mock --session-id <session_id>
```

对话中恢复：

```text
/resume
```

## 审批队列

workflow 产生可审查改动时，MAO 会创建 approval items。

你可以：

- 查看队列
- 打开某项
- 查看带颜色的 diff
- 批准
- 拒绝
- 暂放当前项，先去看别的项

当前交互格式：

```text
Review choice: y=yes / n=no / d=defer / b=back
```

## Merge Candidate

批准后的修改会应用到 integration worktree，并生成 merge candidate。

查看：

```powershell
mao merge list
```

当前 merge 流程是：

`approval -> integration apply -> merge candidate`

还没有自动 merge 回目标分支。

## Capability Registry

MAO 通过自己的 registry 管理 skill 和 MCP：

- `runtime/registry/skills.json`
- `runtime/registry/mcp_servers.json`

### Skill 命令

```powershell
mao skills import-local
mao skills list
mao skills show mcp-builder
mao skills register demo_skill --description "demo skill" --path C:\demo\SKILL.md
mao skills grant demo_skill --role frontend
```

### MCP 命令

```powershell
mao mcp import-local
mao mcp list
mao mcp show mao_mcp
mao mcp register demo_mcp --transport streamable-http --url http://localhost:8123/mcp
mao mcp grant demo_mcp --role reviewer
```

### Policy 命令

```powershell
mao policy show
```

## 直连与中转

MAO 同时支持：

- 官方 API 直连
- 通过 `base_url` 访问中转 / 网关

provider 配置可包含：

- `api_key_env`
- `base_url`
- `extra_headers`

## 当前边界

当前已经比较强的部分：

- 规划
- 前后端协作
- reviewer 与 repair
- 审批队列
- capability registry
- session 恢复

仍在继续增强：

- 真正 merge 回目标分支
- shared file integration actor
- 更强 UI
- 更自然的 skill / MCP 对话式管理
