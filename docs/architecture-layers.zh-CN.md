# 架构分层图

## 概览

MAO 当前仍然是单仓、单进程、CLI-first 形态，但内部已经形成了清晰分层，后续可以继续拆成独立服务。

## 分层结构

```text
用户 / 操作员
  |
  v
Chat CLI / Commands
  |
  v
Session Layer
  - session memory
  - task memory
  - review memory
  - approval queue
  - session resume
  |
  v
Orchestrator Layer
  - architect / frontend / backend / reviewer
  - repair loop
  - ownership checks
  - approval decisions
  |
  +----------------------+
  |                      |
  v                      v
Capability Layer         Integration Layer
  - provider config        - integration worktree
  - skill registry         - merge candidates
  - MCP registry           - shared file actor rules
  - capability policy      - apply / queue / review
  |
  v
Provider Layer
  - OpenAI
  - Anthropic
  - Gemini
  - OpenRouter / base_url gateways
  |
  v
External Model APIs
```

## 当前模块

- `chat.py`
  交互式对话入口
- `sessions.py`
  会话状态、分层记忆、审批队列
- `orchestrator.py`
  主工作流引擎和执行约束
- `registry.py`
  统一 skill / MCP 注册表
- `providers.py`
  模型 provider 调用层
- `gitops.py`
  worktree 与文件落地辅助
- `mergeflow.py`
  merge candidate 存储层

## 为什么仓库还不算“很大”

- 目前仍然以 CLI-first 为主
- 很多边界已经在代码层拆分，但还没有独立成单独服务
- 这样可以保证迭代速度，同时为后续服务化保留空间

## 后续可能继续拆出的目录

- `approval/`
- `integration/`
- `capabilities/`
- `storage/`
- `ui/`
- `services/`

只有当边界足够稳定时，才值得继续拆成更多服务或目录。
