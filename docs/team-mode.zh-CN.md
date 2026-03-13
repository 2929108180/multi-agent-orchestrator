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

## Skill 支持

- 会发现本地 skill
- 可导入 MAO 自己的 registry
- chat 中可通过 `/skills` 查看
- 后续 capability policy 会进一步限制角色或模型可见能力

## Session 支持

- chat session 会本地保存
- 近几轮会话会进入 session/task/review memory
- 支持按 session id 或 `--resume-latest` 恢复
- 恢复时可回放已保存的聊天记录
