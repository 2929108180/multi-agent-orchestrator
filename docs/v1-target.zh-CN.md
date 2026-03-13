# V1 目标

## 目标

交付一个本地 CLI，使其可以完成第一版跨厂商编码代理协作流程。

## 用户结果

用户输入一个需求后，可以得到：

- architect 计划
- frontend 输出
- backend 输出
- reviewer 结论
- 本地保存的运行产物

## 验收标准

- 从 YAML 加载工作流配置
- 至少支持四个角色：architect / frontend / backend / reviewer
- 模型调用通过统一 gateway
- 支持 mock 模式，无需外部 key
- 能从配置和环境变量验证 live provider 就绪情况
- 可选使用独立 Git worktree
- 提供本地 MCP server
- 支持已保存会话与恢复
- 支持 capability registry、导入、注册与授权
- 保存 `run.json`、`summary.md`、`integration.json`、`merge_candidates.json`
- 仓库中能直接看到当前进度

## 延后到 V1 之后

- 自动 merge 到目标分支
- 更完整的 shared file integration actor
- 更细粒度 patch / merge
- Web 或桌面 UI
