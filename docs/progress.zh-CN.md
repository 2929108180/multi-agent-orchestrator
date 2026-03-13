# 进度

## 固定基线

- [x] CLI-first 方向已确定
- [x] 核心工作流形态已确定
- [x] 现成积木优先的原则已确定
- [x] 长期架构已写入仓库

## V1 交付清单

- [x] 初始化 Python CLI 项目
- [x] 增加本地文档和可见范围
- [x] 增加结构化配置模型
- [x] 增加 architect / worker / reviewer 工作流模型
- [x] 增加 provider gateway 抽象
- [x] 增加 mock 多代理工作流
- [x] 增加 live 多 provider 预检
- [x] 增加 Git worktree 集成
- [x] 增加 MCP 工具集成
- [x] 增加结构化 review-to-repair routing
- [x] 增加 chat session memory 和 resume
- [x] 增加本地 skill 发现与 registry
- [x] 增加审批策略与 diff 审批队列
- [x] 增加 merge candidate / merge list
- [ ] 更完整的目标分支 merge 管理

## 安全基线

- [x] MCP 触发执行限制在 mock
- [x] 配置路径限制在项目根目录
- [x] run id 校验
- [x] 文本长度限制
- [x] worker 所有权边界
- [x] 共享文件 integration 规则

## 当前主线

`chat session -> contextual workflow -> approval queue -> integration apply -> merge candidate`
