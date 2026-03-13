# Multi-Agent Orchestrator

[English](./README.md) | 简体中文 | [한국어](./README.ko-KR.md)

面向跨厂商编码代理的本地优先协作系统。  
MAO 的目标不是再造一个单模型聊天工具，而是把多个模型、技能、MCP 工具、审批策略、集成流程统一到同一个团队式工作流里。

## 为什么选择 MAO

- 跨厂商协作
  你可以让不同厂商的模型分别承担规划、前端、后端、审查等角色，而不是被单一模型能力边界锁死。
- 本地优先
  会话、运行记录、审批队列、技能注册表、MCP 注册表都保存在本地，便于审计、迁移和恢复。
- 能力统一接管
  skill、MCP、审批策略、权限和能力暴露由 MAO 自己管理，而不是依赖模型厂商“也许提供、也许不提供”的行为。
- 团队模式
  MAO 把模型当作一支 AI 团队来调度，而不是把所有事都丢给一个模型自由发挥。
- 可审查、可暂停、可恢复
  你可以看到 diff、排队审批、暂放当前改动，再去审另一个模型的改动，之后继续回来处理。

## 核心能力

- 多模型团队编排
  `architect / frontend / backend / reviewer`
- 分层记忆
  `session memory / task memory / review memory`
- 会话恢复
  支持 `--resume-latest`、`--session-id` 和对话内 `/resume`
- 审批策略
  支持团队默认、角色覆盖、模型覆盖
- diff 审批队列
  支持 `/queue`、`/pick`、`/approve`、`/reject`、`/defer`
- integration worktree
  审批通过后的改动会落到独立 integration 工作区
- capability registry
  skill 与 MCP 统一注册、导入、查看、授权
- 直连与中转
  同时支持官方 API 和 `base_url` 中转网关

## 当前特色能力

### 1. 团队式工作流

一轮典型执行链路：

1. 用户提出需求
2. `architect` 生成计划与共享契约
3. `frontend` 与 `backend` 并行生成方案或改动提案
4. `reviewer` 做一致性检查并生成 defect
5. 系统将 defect 精准路由回对应角色
6. 审批队列对可应用改动进行人工或自动决策
7. 已批准改动进入 integration worktree

### 2. 冲突防护

MAO 不接受多个 worker 无约束地改同一文件。当前已具备：

- `allowed_paths / restricted_paths`
- 共享文件识别
- 冲突文件识别
- integration layer 决策
- 审批策略驱动的 `auto / manual / reject`

### 3. 统一能力层

MAO 的方向不是让模型自己“猜”它有哪些 skill 或 MCP，而是：

- 本地可发现
- 显式导入 registry
- 统一授权
- 按角色或模型控制可见性

这样可以降低迁移成本，同时避免运行时能力源不清晰。

## 常用命令

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
```

## 对话模式

`mao chat` 目前支持：

- 会话记忆与恢复
- 连续对话上下文注入
- 实时工作流阶段展示
- 本地 skill / MCP 查询
- 审批队列与 diff 审查
- integration worktree 写入

常用对话命令：

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

正式运行时优先使用 MAO 自己的 registry：

- `runtime/registry/skills.json`
- `runtime/registry/mcp_servers.json`

本地扫描现在只是“导入来源”，不是正式运行时的唯一真相源。

这意味着：

- 你可以导入现有本机 skill / MCP
- 也可以手动注册新的 skill / MCP
- 还能按角色或模型分配访问权限

## Live Provider 支持

MAO 支持两种接入方式：

- 直接访问官方 API
- 通过 `base_url` 访问中转 / 兼容网关

你可以在统一 provider config 中配置：

- `api_key_env`
- `base_url`
- `extra_headers`
- 审批策略

## 适合谁使用

- 想把多个模型组织成一个开发团队的个人开发者
- 想降低单模型能力上限的团队
- 需要本地审计、审批、恢复和能力治理的工程团队
- 想把 skill、MCP、审批和会话统一管理的 AI 工程实践者

## 当前阶段说明

MAO 已经具备“可以认真试用”的基础能力，但仍在持续增强。  
当前已经很好用在：

- 需求拆解
- 架构设计
- 前后端接口对齐
- 审查与修复循环
- 审批与 integration 管理

还会继续增强：

- 更细粒度的 patch / merge
- 更强的 shared file integration actor
- 更完整的目标分支合并流程
- 更漂亮的审批交互界面
- 更自然的 skill / MCP 对话式安装和注册体验

## 开发与验证

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
```

## 相关文档

- [README.md](./README.md)
- [README.ko-KR.md](./README.ko-KR.md)
- [docs/architecture-baseline.md](./docs/architecture-baseline.md)
- [docs/progress.md](./docs/progress.md)
- [docs/team-mode.md](./docs/team-mode.md)
