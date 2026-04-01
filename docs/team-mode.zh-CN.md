# 团队模式

## 目标

把 MAO 当作一支本地 AI 团队来协作，而不是单个模型聊天器。

## 当前团队角色

- `architect`
  负责规划和共享契约
- `frontend`
  负责前端与 UI 相关路径
- `backend`
  负责后端与 API 相关路径
- `reviewer`
  负责一致性审查和 defect 路由

## 当前约束

- frontend / backend 各自带有 `allowed_paths`
- frontend / backend 各自带有 `restricted_paths`
- shared file 不会直接下发给普通 worker
- 开启 worktree 时，worker 在独立工作区中执行

## Skill + MCP Tool 支持

- 会发现本地 skill
- skill 可绑定到 MCP tool（Skill -> MCP 间接执行），使模型在运行过程中可调用
- chat 中可通过 `/skills` 查看，并用 `/bind-skill <skill> <server> <tool>` 绑定

## 团队运行中的工具调用

- team workflow 与 single-model chat 都支持工具执行循环
- 模型用文本块协议（`TOOL_CALL`）请求工具，MAO 执行后回灌 `TOOL_RESULT` 再继续生成
- 工具可用性会按 registry 中 role/model 的 allowlist 过滤
- **architect 超级权限**：architect 永远能看到/调用所有已注册的 skills 与 MCP servers（但仍尊重 `enabled=false` 作为全局关停开关）

## 主管压缩分发（不广播原文）

- 只有 architect/supervisor 会看到用户原始输入
- 下发给 worker 前，先由 architect 生成 role-specific briefs
- frontend/backend/integration/reviewer 只接收 brief + shared contract + 约束，而不是用户原文

## Session 支持

- chat session 会本地保存
- 近几轮会话会进入 session/task/review memory
- MAO 还会持久化每个角色的 `Role memory:`（frontend/backend/integration/reviewer 的 bounded 摘要），并在后续运行注入到对应 worker prompt
- 支持按 session id 或 `--resume-latest` 恢复
- 恢复时可回放已保存的聊天记录
