# 变更记录（2026-03-16）

本文记录本轮在 **Multi-Agent Orchestrator (MAO)** 仓库内完成的主要改动点，便于回溯与验收。

> 覆盖范围：workflow（integration/reviewer/repair）、config/runtime_root 对齐、session 导出、MCP registry + client 执行链路、测试与文档同步。

---

## 1. Workflow：Integration 报告结构化 + Reviewer 以 Integration 为主 + Repair 轮次重跑 Integration

### 1.1 结构化 Integration 输出协议（非 JSON，块格式）
- 在 orchestrator 中定义并注入 `INTEGRATION_PROTOCOL_V1`（块格式输出），并在 worker prompt 渲染时支持按 task 注入 `response_protocol`。

### 1.2 Integration 报告解析与持久化
- 新增 `parse_integration_report(...)`：逐行解析 Integration 输出块（包含 bindings / issues / open_questions 等）。
- run artifacts：
  - `integration.json` 保持 `decisions` 向后兼容
  - 新增 `reports`：保存每轮的结构化 integration report（以及 raw_text/model/round_index）。

### 1.3 Reviewer Prompt 调整
- Reviewer prompt 调整为：
  - **Integration report（PRIMARY）**
  - FE/BE response（REFERENCE）

### 1.4 Repair Loop 行为调整
- 在每次 reviewer 之前 **重跑 integration**，并将当轮 integration report 作为 reviewer 的主输入。

### 1.5 相关文件
- `src/mao_cli/core/models.py`
  - 新增/扩展：`WorkerTask.response_protocol`、`IntegrationBinding`、`IntegrationReport`、`WorkflowRun.integration_reports`
- `src/mao_cli/orchestrator.py`
  - integration 协议注入、解析、repair loop rerun integration、review prompt 以 integration 为主、artifact 扩展
- `src/mao_cli/providers.py`
  - mock integration / reviewer 输出与新协议对齐
- `tests/test_workflow.py`
  - 新增 integration report parser 测试、更新 workflow/artefact/events 断言

---

## 2. 配置对齐：runtime_root（以及部分 artifacts_root）不再被硬编码

### 2.1 CLI：`--config` 影响 runtime_root
- CLI 多个子命令增加/对齐 `--config/-c`，用于计算 runtime_root，避免隐式绑定 `configs/local.example.yaml`。

### 2.2 MCP tools：增加 `config_path` 以一致解析 runtime_root
- MCP server 暴露的会话/技能相关工具增加 `config_path`（可选），用于在 tool 内部 `load_config()` 计算 runtime_root。

### 2.3 runs 工具对齐 artifacts_root
- MCP runs 相关读取从 config 推导 `artifacts_root`，避免仅在默认 `artifacts/runs` 下可用。

### 2.4 相关文件
- `src/mao_cli/main.py`
- `src/mao_cli/mcp_tools.py`
- `src/mao_cli/mcp_server.py`
- `docs/modules/registry/README.md`
- `docs/mcp-integration.md`

---

## 3. Sessions：导出 session transcript 为 Markdown

### 3.1 CLI
- 新增/完善：`mao session export <session_id>`

### 3.2 Chat
- 新增 `/export` 命令：导出当前会话 transcript 为 markdown。

### 3.3 相关文件
- `src/mao_cli/sessions.py`
  - `export_session_markdown(...)`
- `src/mao_cli/chat.py`
  - `/export` + 落地导出实现
- `src/mao_cli/main.py`
  - `mao session export`
- `docs/modules/sessions/README.md`
- `docs/modules/chat/README.md`
- `tests/test_workflow.py`
  - 新增 chat export 测试

---

## 4. MCP：补齐“可调用”执行链路（类似 Claude Code 的工具调用体验的地基）

### 4.1 新增 MCP client（本地执行层）
- 新增 `src/mao_cli/mcp_client.py`
  - 支持 `stdio` / `streamable-http` transport
  - 支持列出 tools 与调用 tool

### 4.2 新增 CLI 命令
- `mao mcp call <server> <tool> [--args JSON | --args-file path.json]`
- `mao mcp tools <server>`：列出 MCP server 暴露的工具与 input schema

### 4.3 本地 MCP server 注册记录稳定化
- `import_local_mcp` 注册的本地 server 启动方式改为使用 `sys.executable -m ...`，减少对 PATH 中 `mao` 脚本存在的依赖。

### 4.4 相关文件
- `src/mao_cli/mcp_client.py`
- `src/mao_cli/main.py`
- `src/mao_cli/registry.py`
- `docs/mcp-integration.md`
- `docs/modules/registry/README.md`

---

## 5. 测试状态
- 当前 `pytest -q` 在本仓库内通过（mock 流程覆盖为主）。

---

## 6. 未完成点（待推进）

以下是我们之前讨论过、但当前还未完成/未完全落地的事项清单（作为后续迭代 backlog）：

### 6.1 Tool/Skill 真正“会调用”（目标：接近 Claude Code 体验）
- ✅ tool-call 执行循环（`TOOL_CALL`/`TOOL_RESULT`）已在 team workflow 与 single-model chat 中落地。
- ✅ `architect` 角色具备超级权限：可见/可调用所有已注册 skills 与 MCP servers（仍尊重 `enabled=false`）。
- ✅ 新增 `mao_fs`（architect-only）文件系统 MCP 工具，使 single-model 模式具备项目根目录内的文件 CRUD（带确认与 `.git` 护栏）。
- skill 目前仍以 `SKILL.md` 为“说明/能力描述”为主，运行期语义主要通过 "Skill -> MCP tool" 绑定实现；后续若要支持更多 skill 运行形态（prompt macro / 多步 skill runtime），仍需扩展。

### 6.2 Supervisor ↔ Worker 交互优化
- supervisor 仍可能把用户输入完整广播给所有 worker；需要更结构化的拆解/压缩与任务分发策略。

### 6.3 UI/UX（终端交互体验）
- 已为 TTY 交互终端补齐最小可用的等待状态（Rich status spinner）：
  - single-model 回复（calling architect）
  - live 模式下 supervisor 路由判定（TEAM_MODE 决策）
- 仍未实现真正的 token streaming / Live 仪表盘式 UI（保持 event 行输出与测试稳定）。

### 6.4 配置系统的 overlay / 多配置来源
- 目前主要是单 YAML config；还未实现 base + override / env overlay 等更强配置合并策略。

### 6.5 MCP 生态完善
- 已补齐 CLI 侧 call/tools，但：
  - 仍缺少将 MCP 调用能力开放给 workflow 模型（即模型能自主调用）。
  - 仍缺少更完善的权限/审批策略与调用审计（谁在何时调用了什么）。

### 6.6 Runs 索引/搜索
- `docs/progress.md` 中的 "Add persistent run index and search" 仍未完成。

---

## 7. 备注
- 本轮同时包含若干 docs/modules 文档同步更新，用于反映功能落地状态（sessions/chat/registry 等）。


另外 ，你帮我检查一下目前skill(导入、调用、对话下载)和mcp 我们打算mcp和skill也能够统一管理以及记忆(恢复会话后 是否会打印出之前的记录、恢复后 子模型(也就是执行者)的会话记忆是否会恢复) 会话恢复
配置文件管理 以及用户体验性上的这些内容（比如 模型在加载回复时 是否有等待时的等待动画 而不是就空着什么也没有） 是否已经完善 ，目前我们有一个专门的配置文件 live.packyapi.yaml                          
我希望目前代码中不能只兼容这一种方式；还有就是主管模型和子模型的交互 比如用户提出需求 主管模型应该进行拆分 将对应内容压缩编辑 分给对应角色 ，不能把用户输入的原文给到两位模型，且他们都应该有记忆    
在同一次会话（用户改动多次一个位置代码）或者用户关闭终端但是又恢复后 主模型和下面的子模型 不能什么都不记得；我们这个项目后期不止于编码场景 因此角色场景不能限制死，要么就是读配置文件                  
要么就是其他方式；我问这么多 就是想知道准确的知道 当前这个项目进度到哪里了、