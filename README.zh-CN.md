# Multi-Agent Orchestrator

面向跨厂商编码代理的本地优先编排系统。

[English](./README.md) | 简体中文 | [한국어](./README.ko-KR.md)

## 目标

- 接收产品或开发需求
- 生成执行计划和共享契约
- 将前端、后端、审查任务分发给不同模型
- 运行审查、修复、审批和集成流程
- 保存完整运行记录、会话和能力注册表

## 常用命令

```powershell
mao chat --mock
mao chat --live --config configs/live.multi-provider.example.yaml
mao skills import-local
mao mcp import-local
mao skills list
mao mcp list
mao policy show
```

## 对话模式

`mao chat` 现已支持：

- 会话记忆与恢复
- 审批队列与 diff 审查
- skill / MCP 注册表查询
- 团队模式上下文

常用聊天命令：

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

## 能力注册表

正式运行时优先使用 MAO 自己的 registry：

- `runtime/registry/skills.json`
- `runtime/registry/mcp_servers.json`

本地 skill / MCP 可通过导入进入 registry，而不是直接作为运行时真相源。
