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
- `mao_list_mcp_servers`
  列出已注册 MCP servers（registry introspection）
- `mao_read_mcp_server`
  读取单个 MCP server 的 registry 记录
- `mao_write_team_note`
  追加团队备注
- `mao_write_session_note`
  追加会话备注
- `mao_trigger_mock_workflow`
  触发本地 mock 工作流

## 文件系统 MCP（mao_fs）

`mao_fs` 是一个 **仅对 `architect` 角色可见** 的 MCP server（通过 registry allowlist 控制），用于在 single-model 模式下直接对项目文件进行 CRUD。

提供的工具：

- `mao_fs_list_dir`：列目录
- `mao_fs_read_text`：读文本
- `mao_fs_write_text`：写文本（覆盖需 `overwrite=true` + `confirm="YES"`）
- `mao_fs_mkdir`：建目录
- `mao_fs_delete_file`：删文件（需 `confirm="DELETE"`）
- `mao_fs_delete_dir`：删目录（需 `confirm="DELETE"`，可 `recursive=true`）

安全护栏：

- 仅允许操作项目根目录内路径
- 拒绝任何指向 `.git/` 的读写删
- 拒绝删除项目根目录

## 传输方式

- `stdio`
  适合本地 MCP client 启动子进程接入
- `streamable-http`
  适合浏览器、调试工具或本地 HTTP 方式接入

## 说明

- 当前 MCP 层仍然是本地优先
- 它不替代 CLI
- 它是后续 team mode、registry、integration 和工具能力扩展的标准接入口
- CLI 可用 `mao mcp call` 调用 registry 中的 MCP tool
- team workflow 与 single-model chat 也可通过跨 provider 的 `TOOL_CALL` 文本协议调用 MCP tool（受 registry allowlist 约束；architect 角色可 bypass allowlist）

## MCP 自动发现来源

`mao mcp import-local` 会按顺序扫描以下位置：

1. **内置**：`mao_mcp` + `mao_fs`（始终存在）
2. **项目 manifest**：`<project_root>/.mcp.json`
3. **Claude Desktop**：`%APPDATA%/Claude/claude_desktop_config.json`（Windows）或 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）
4. **Claude Code settings**：`~/.claude/settings*.json` 中的 `mcpServers` 字段
5. **Claude Code MCP servers 目录**：`~/.claude/mcp-servers/*.py` — 每个 `.py` 文件注册为一个 stdio MCP server（server name = 文件名去掉 `.py`）

所有来源以非破坏性方式合并：已有的 roles/models/enabled 等权限配置不会被覆盖。
