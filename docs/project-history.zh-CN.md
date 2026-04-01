# 项目完整事项记录

## 说明

这份文档用于记录 **Multi-Agent Orchestrator (MAO)** 从项目启动到当前阶段已经完成的主要事项。  
目标不是只记最新改动，而是把“从一开始到现在的完整脉络”沉淀下来，方便后续持续维护、回顾和扩展。

## 一、项目定位

MAO 的核心目标从一开始就是：

- 构建一个 **本地优先**
- **跨厂商多模型协作**
- **团队式工作流**
- **可审查、可恢复、可治理**
- 面向编码任务，但架构上不永久绑定“前后端”这类固定角色

项目不是为了再造一个单模型聊天工具，而是为了把：

- 模型
- skill
- MCP
- 审批策略
- 集成流程
- 会话记忆

统一成一套可以长期演进的能力层和工作流系统。

## 二、最初阶段完成的基础骨架

项目启动后，最先完成的是 CLI-first 基础骨架：

- 建立 Python CLI 工程结构
- 引入 `Typer` 作为命令入口
- 引入 `Rich` 作为终端展示层
- 引入 `Pydantic` 作为配置与状态模型层
- 引入 `LiteLLM` 作为多 provider 模型调用统一入口
- 建立基础测试
- 建立 `README` 与初版技术设计文档

当时的目标是：先把项目做成一个 **可安装、可运行、可扩展** 的本地 CLI，而不是一上来做复杂 Web 平台。

## 三、第一版工作流闭环

随后完成了第一条最小闭环：

- `architect`
- `frontend`
- `backend`
- `reviewer`

形成了：

`需求 -> 拆解 -> 前后端并行 -> reviewer 审查 -> 修复闭环 -> 本地产物`

这一阶段完成的关键能力：

- mock 模式下多角色工作流
- reviewer 可以发现前后端不一致
- defect 可回传给对应角色
- 修复后可再审
- 运行产物持久化到本地

这是系统第一次从“命令工具”变成“团队工作流”的关键节点。

## 四、Provider 配置与 live 前置能力

之后完成了多 provider 配置与环境预检：

- 配置文件支持按角色绑定 provider
- 支持不同模型厂商
- 支持环境变量读取 key
- 支持 `base_url`
- 支持额外 header
- 支持 `doctor`
- 支持 `validate`

同时也明确了长期原则：

- 正式运行时不依赖厂商本地工具私有配置
- 使用 MAO 自己维护的统一 provider config
- 支持官方直连
- 支持中转 / 网关 / 兼容入口

## 五、Git worktree 与隔离执行

项目引入了 `git worktree` 能力，完成：

- frontend / backend 独立工作区
- worker 输出可隔离
- 运行产物记录 worktree 路径
- 为后续审批与 merge 打基础

这一步是系统从“只会协调文本输出”向“面向真实代码仓库工作流”前进的重要基础。

## 六、MCP 集成基础层

项目后来接入了本地 MCP server 和工具层，完成：

- `mao mcp-serve`
- 通过 FastMCP 暴露本地工具
- 项目状态读取
- 文档读取
- run 列表/摘要
- session 相关读取
- 团队 note / session note 写入

同时我们也确定了原则：

- MCP 不依赖厂商是否“天然支持”
- MAO 自己维护统一能力暴露层

## 七、结构化审查与修复闭环

在 reviewer 部分，我们把“文本审查意见”升级成更结构化形式：

- defect 模型
- owner
- severity
- summary
- action

然后按角色做 repair routing：

- frontend 缺陷只发给 frontend
- backend 缺陷只发给 backend
- shared 缺陷走 shared 路径

这一步让系统从“自由文本聊天协作”变得更像一个真正的工程流程系统。

## 八、安全基线

随后补了一批基础安全边界：

- `config` 路径限制在项目根目录
- run id 校验
- 输入长度限制
- 文本清洗
- MCP 默认只触发 mock workflow
- provider 就绪检查

这一步不是花哨功能，但决定了系统后续能不能继续扩展而不失控。

## 九、交互式 `mao chat`

项目从命令式执行进入了对话式执行：

- 增加 `mao chat`
- 持续会话模式
- slash command
- 会话内命令帮助
- 状态查看
- provider 检查
- run 执行

这使 MAO 从“手动触发器”变成真正可交互的团队工作台。

## 十、会话记忆与恢复

之后项目又完成了：

- session 保存
- `--resume-latest`
- `--session-id`
- `/history`
- `/context`
- `/last`
- `/resume`

并逐步形成了分层记忆体系：

- `session memory`
- `task memory`
- `review memory`

这一步的意义在于：

- 会话恢复后不只是内部状态恢复
- 新一轮任务也能带着之前的上下文继续进行

## 十一、审批队列与 diff 审查

项目后续进入了更接近真实工程系统的阶段，完成：

- diff-based approval queue
- `/queue`
- `/pick`
- `/review`
- `/approve`
- `/reject`
- `/defer`

并且支持：

- 打开某一个审批项
- 看改前/改后 diff
- 批准 / 拒绝 / 暂放
- 先去看别的审批项，再回来继续

这一步是 MAO 从“只会判断”进化到“可审查、可操作”的关键阶段。

## 十二、integration worktree 与 merge candidate

批准后的改动不会直接写回主工作区，而是：

- 先进入 integration worktree
- 再生成 merge candidate
- 支持 `mao merge list`

并且：

- shared file 不直接应用
- shared file 进入 integration actor 路径

这一步意味着系统已经具备：

- 审批
- 应用到 integration
- 候选合并

三层基础能力。

## 十三、Capability Registry 正式建立

在 skill / MCP 方面，后来完成了统一注册表层：

- skill registry
- MCP server registry
- local import
- register
- show / list
- grant

CLI 命令包括：

- `mao skills import-local`
- `mao skills list`
- `mao skills show`
- `mao skills register`
- `mao skills grant`
- `mao mcp import-local`
- `mao mcp list`
- `mao mcp show`
- `mao mcp register`
- `mao mcp grant`
- `mao policy show`

同时，chat 中也支持：

- `/skill-import-local`
- `/mcp-import-local`
- `/register-skill`
- `/register-mcp`
- `/grant-skill`
- `/grant-mcp`

这一步的意义是：

- 本地 skill / MCP 可导入
- registry 成为正式能力源
- MAO 不再依赖模型“自己知道什么能力”

## 十四、文档体系建设

项目后续补齐了较完整的文档系统：

- 英文 README
- 简体中文 README
- 韩文 README
- 用户手册
- 测试手册
- 架构基线
- 架构分层图
- 安全基线
- MCP 集成文档
- 团队模式文档
- 技术设计文档
- V1 目标文档

并补充了：

- `docs/README.md`
- `docs/modules/`

用于按模块沉淀功能和后续计划。

## 十五、`docs/modules/` 模块沉淀目录

目前已建立：

- `chat`
- `team`
- `registry`
- `approval`
- `integration`
- `providers`
- `sessions`

这一步的目的不是新功能，而是解决一个真实问题：

> 很容易忘记我们已经做了什么，以及之后还要补什么

所以从这里开始，模块级文档就是系统长期维护的一部分。

## 十六、团队模式控制

项目还增加了团队模式控制层：

- `team=on`
- `team=off`
- `team=auto`

原则已经明确：

- 用户显式设置优先级最高
- 自动判断只存在于 `auto`

另外增加了成员控制：

- `/members`
- `/member on <role>`
- `/member off <role>`

当前成员包括：

- frontend
- backend
- integration
- reviewer

这一步意味着团队工作流不再是“一刀切”。

## 十七、交互可观测性增强

我们还补了：

- loading state
- dispatch summary
- response summary
- final recap

所以用户现在在 chat 中不再只是看到：

- completed

而是能看到：

- 谁在执行
- 主管发了什么
- 每个角色回了什么摘要
- 最终 recap

## 十八、Integration Actor 正式引入

这是最新推进的主线之一。

我们已经不再把 integration 只看成隐式规则，而是：

- 加入正式角色集合
- 进入配置层
- 进入计划模型
- 进入工作流顺序
- 进入模块文档

当前顺序是：

`architect -> frontend/backend -> integration -> reviewer`

这意味着：

- frontend / backend 先各自产出
- integration actor 负责做契约绑定
- reviewer 再审查最终一致性

虽然还没达到最终成熟形态，但它已经不再是隐含逻辑，而是系统里的一级成员。

## 十九、当前已经完成的主要功能清单

截至当前，MAO 已完成的主要能力包括：

- CLI-first 工程骨架
- mock 工作流
- live provider 配置
- provider 预检
- worktree 隔离
- MCP server
- 结构化 defect
- repair routing
- 安全基线
- `mao chat`
- 会话记忆
- 会话恢复
- transcript 回放
- diff 审批队列
- integration worktree
- merge candidate
- capability registry
- 本地导入 skill / MCP
- chat 内 capability 管理
- 多语言 README
- 中文 docs
- docs/modules 模块沉淀
- 团队模式开关
- 成员单独开关
- integration actor 正式引入

## 二十、当前仍在继续推进的方向

虽然完成了很多，但还没有“彻底完成”的方向包括：

- integration actor 更深度职责化
- shared file integration actor 的更完整流程
- 更细粒度的 merge / branch 管理
- 真正的目标分支 merge apply
- 更自然的非编码任务角色抽象
- provider profile 的进一步完善
- 更成熟的审批 UI
- 更完整的会话 transcript 回放保真

## 二十一、当前项目阶段判断

当前 MAO 已经不再是单纯的原型，而是：

**一个可以认真试用的、多模型团队协作与审批编排系统骨架**

它已经具备：

- 运行主线
- 能力层
- 审批层
- 集成层
- 会话层
- 文档层

虽然还在继续增强，但已经具有明确的长期演进方向。
