# 安全基线

## 当前防护

- MCP 触发的 workflow 默认仅允许 mock 模式
- CLI 与 MCP 使用的配置路径必须位于项目根目录内
- 读取 run 产物前要校验 run id
- requirement 与 defect 文本长度受限
- worker 具备文件所有权边界
- shared file 必须走 integration actor 规则

## 为什么先做这些

- 防止路径穿越和意外文件访问
- 防止通过 MCP 直接暴露 live key 和成本
- 控制 prompt 和产物膨胀
- 防止多个 worker 无约束改同一文件

## 后续仍可继续加强

- 更细粒度的 MCP 工具白名单
- secrets 脱敏
- 更严格的 merge / branch 审批
- shared file 的专门 integration actor
