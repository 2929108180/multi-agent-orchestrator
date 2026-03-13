# MCP 集成

## 目标

通过本地 MCP server 暴露当前项目状态、运行记录和工作流入口。

## 当前 MCP 工具

- `mao_project_status`
  读取当前项目进度
- `mao_read_project_doc`
  读取指定项目文档
- `mao_list_runs`
  列出最近运行记录
- `mao_read_run_summary`
  读取某次运行摘要
- `mao_list_sessions`
  列出已保存会话
- `mao_read_session`
  读取单个会话
- `mao_list_skills`
  列出已注册 skill
- `mao_read_skill`
  读取单个 skill
- `mao_write_team_note`
  追加团队备注
- `mao_write_session_note`
  追加会话备注
- `mao_trigger_mock_workflow`
  触发本地 mock 工作流

## 传输方式

- `stdio`
  适合本地 MCP client 启动子进程接入
- `streamable-http`
  适合浏览器、调试工具或本地 HTTP 方式接入

## 说明

- 当前 MCP 层仍然是本地优先
- 它不替代 CLI
- 它是后续 team mode、registry、integration 和工具能力扩展的标准接入口
