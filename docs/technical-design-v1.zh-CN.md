# 技术设计 v1

## 产品方向

系统是一个 CLI-first 的跨厂商编码代理编排层。  
它用于协调多个模型 provider 之间的规划、执行、审查、修复与审批，并在本地留下完整轨迹。

## 核心原则

- CLI-first，后续再补更强 UI
- 本地优先执行与日志
- 契约优先，而不是只靠 prompt
- worker 之间要有明确边界
- 机器检查优先于模型审查

## 规划模块

- `cli`
  命令入口与交互层
- `core`
  工作流模型与状态
- `providers`
  provider adapter 与路由
- `orchestrator`
  plan / dispatch / review / repair
- `mcp`
  MCP 能力层
- `gitops`
  worktree / apply / integration
- `storage`
  run、session、registry、merge candidate

## v1 里程碑

1. 建立包结构与基础 CLI
2. 本地状态与运行目录
3. planner 与 task spec
4. 多 provider gateway
5. worker 执行闭环
6. reviewer 与 repair loop
7. Git / integration 流程
8. capability registry
9. 审批与 merge candidate
