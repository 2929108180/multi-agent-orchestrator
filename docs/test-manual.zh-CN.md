# 测试手册

[English](./test-manual.md) | 简体中文 | [한국어](./test-manual.ko-KR.md)

## 目标

这份手册用于验证 MAO 的完整功能链路，包括：

- 基础环境
- mock 工作流
- 会话记忆
- 审批队列
- skill / MCP 注册表
- merge candidate
- live provider 预检

## 推荐测试顺序

建议按以下顺序测试：

1. 基础环境
2. mock 工作流
3. 会话记忆与恢复
4. 审批队列
5. registry 管理
6. merge candidate
7. live provider 预检

## 1. 基础环境

```powershell
cd E:\Ai\multi-agent-orchestrator
mao --help
mao status
mao doctor --mock
```

预期：

- 命令正常显示
- `status` 显示关键能力已实现
- `doctor` 显示 mock provider ready

## 2. Mock 工作流

```powershell
mao chat --mock
```

输入：

```text
做一个带任务列表和状态筛选的任务管理器
/exit
```

预期：

- 能看到 workflow 阶段信息
- 生成 run 目录
- 返回 summary
- 提示 approval queue 数量

## 3. 会话记忆与恢复

第一次会话：

```powershell
mao chat --mock
```

输入：

```text
做一个任务管理器
/exit
```

恢复最近会话：

```powershell
mao chat --mock --resume-latest
```

然后输入：

```text
/history
/context
/last
/exit
```

预期：

- `/history` 能看到至少一轮历史
- `/context` 能显示摘要上下文
- `/last` 能显示最近一次 run

注意：

- 恢复会话会回放已保存的 transcript（方便你快速恢复上下文）
- 这不是终端滚动历史，而是会话里记录的 transcript

## 4. 审批队列

```powershell
mao chat --mock
```

输入：

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

预期：

- `/queue` 显示待审项目
- `/pick` 显示 diff
- `d` 可以暂放当前项
- `y` 可以批准当前项
- `/merge` 能看到 merge candidate

## 5. Registry 管理

```powershell
mao skills import-local
mao skills list
mao skills show mcp-builder

# MCP import-local 会自动发现：项目 .mcp.json + Claude Desktop 配置（best-effort）
# 并且是 merge 行为：不会覆盖已存在的 enabled/roles/models/tools 权限配置
mao mcp import-local
mao mcp list
mao mcp show mao_mcp

mao policy show
```

预期：

- 本地 skill 能导入 registry
- 本地 MCP 能导入 registry
  - 若 Claude Desktop 配置里存在 `dameng_mcp` 等 stdio MCP，应能被导入
- `list/show` 输出清晰
- `policy show` 显示审批策略

### 5.1 验证 stdio MCP（例如 dameng_mcp）的工具发现与调用

1) 确认 Claude Desktop 配置中存在：

- Windows: `%APPDATA%/Claude/claude_desktop_config.json`
- 结构示例：

```json
{
  "mcpServers": {
    "dameng_mcp": {"command": "python", "args": ["-m", "dameng_mcp"], "env": {"...": "..."}}
  }
}
```

2) 导入并查看：

```powershell
mao mcp import-local
mao mcp list
mao mcp show dameng_mcp
mao mcp tools dameng_mcp
```

预期：

- `dameng_mcp` 出现在列表中
- `mao mcp tools dameng_mcp` 能列出工具（如果 server 支持 `list_tools`）

3) 在对话/工作流中验证 tool-call（需要 server 对当前 role/model 可见）：

- 如需限制可见性：

```powershell
mao mcp grant dameng_mcp --role backend
```

- 然后在 live/team workflow 中观察 `tool -> dameng_mcp.<tool>` 成功执行（以实际工具名为准）。

## 6. 单模型（architect）工具验证

### 6.1 列出 MCP/skills（应先 tool-call 再回答）

```powershell
mao chat --mock
```

输入：

```text
有哪些 MCP 可以用？
有哪些 skills 可以用？
/exit
```

预期：

- 会看到 tool 事件，例如：
  - `architect tool -> mao_mcp.mao_list_mcp_servers`
  - `architect tool -> mao_mcp.mao_list_skills`

### 6.2 单模型文件系统 CRUD（mao_fs）

```powershell
mao chat --mock
```

输入：

```text
/team off
创建 tmp/test.txt 写入 hello
读取 tmp/test.txt
列出 tmp 目录
删除 tmp/test.txt
删除 tmp 目录
/exit
```

预期：

- 会看到 `architect tool -> mao_fs.*` 的调用
- 覆盖/删除需要显式确认字段（confirm=YES / confirm=DELETE），模型会在需要时自动补齐

## 7. 对话中管理能力

```powershell
mao chat --mock
```

输入：

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

预期：

- 导入命令会更新 registry
- `/skills` 显示 skill
- `/mcp` 显示 MCP server
- `grant` 命令成功更新权限

## 7. Merge Candidate

在至少批准过一个变更后运行：

```powershell
mao merge list
```

预期：

- 能看到 merge candidate 列表
- 能看到 status 与 shared 标记

## 8. Live Provider 预检 + Live 全流程

### 8.1 预检（报告 + 严格校验）

使用你的真实配置（例如：`configs/live.packyapi.yaml`）。

报告模式（不 fail fast，适合看清楚缺哪个 env）：

```powershell
mao doctor --config configs/live.packyapi.yaml
```

严格校验（缺任何 key 都会退出码 != 0）：

```powershell
mao validate --config configs/live.packyapi.yaml
```

预期：

- 缺 key 时显示缺失环境变量，并退出非 0
- key 正确时输出 `All configured providers are ready.`

### 8.2 启动 live chat

```powershell
mao chat --live --config configs/live.packyapi.yaml
```

预期：

- 只有在 key 配置完整时才会进入 live chat

### 8.3 Live chat 能力/registry 冒烟测试

进入 live chat 后执行：

```text
/status
/skills
/mcp
/team auto
```

预期：

- skills / MCP 列表能显示
- team_mode 可查询/切换

### 8.4 路由判定 spinner + single-model spinner

1) 自动路由决策（TTY 终端应看到 `Deciding routing...`）：

```text
Hello
```

2) 强制 single-model（TTY 终端应看到 `Thinking...`）：

```text
/team off
总结一下当前项目状态。
```

### 8.5 Live team workflow 全链路

```text
/team on
Build a small task tracker with FE dashboard and BE API.
/exit
```

预期：

- 能看到 architect/frontend/backend/integration/reviewer 的事件输出
- 保存 run artifacts
- 如有决策，approval queue 会更新

## 9. 全量回归

```powershell
pytest
```

预期：

- 所有测试通过

## 故障排查建议

如果出现问题，请优先收集：

- 你执行的命令
- 终端输出
- 最新 run 目录
- `run.json`
- `summary.md`
- `integration.json`
- `integration.md`

如果是会话恢复相关问题，再额外检查：

- `/history`
- `/context`
- `/queue`
