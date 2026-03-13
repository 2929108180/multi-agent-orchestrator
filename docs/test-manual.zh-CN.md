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

- 恢复会话不会自动把旧聊天文本重新打印回终端
- 恢复的是会话状态，不是终端滚动历史

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

mao mcp import-local
mao mcp list
mao mcp show mao_mcp

mao policy show
```

预期：

- 本地 skill 能导入 registry
- 本地 MCP 能导入 registry
- `list/show` 输出清晰
- `policy show` 显示审批策略

## 6. 对话中管理能力

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

## 8. Live Provider 预检

先准备 live 配置：

```powershell
mao validate --config configs/live.multi-provider.example.yaml
```

预期：

- 缺 key 时显示缺失环境变量
- key 正确时预检通过

然后：

```powershell
mao chat --live --config configs/live.multi-provider.example.yaml
```

预期：

- 只有在 key 配置完整时才会进入 live chat

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
