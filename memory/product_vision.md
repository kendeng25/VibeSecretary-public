# 产品愿景备忘

- VibeSecretary 面向 vibe coding 的过程管理、实现理解和 Prompt 优化。
- 三个长期核心需求：治理 `plans/`、`build_hist/` 及用户自定义过程目录；以源码证据
  展示项目真实技术实现；结合过程资料和代码上下文补充、校准开发 Prompt 并提出问题。
- 产品核心应保持本地优先、仓库原生、Git 友好，并避免运行时依赖 `refs/`。
- 首版明确服务 VS Code Terminal + Codex CLI，不建设独立 CLI、桌面/Web 应用或
  VS Code 扩展。
- 首批用户是个人开发者，当前不设计团队协作功能。
- 产品以一个 Codex Plugin 呈现；Skill、Hook、Local MCP Server 是其内部组成，不是
  并列产品入口。默认使用当前 Codex 会话完成 LLM 推理，无需额外 API；正式 v1 应
  支持用户选择自己的 API。Claude Code/OpenCode 等宿主仅保留后续扩展边界。
- Plugin 的可执行实现统一使用 Python。
- 每个项目必须在启用 Plugin 前配置一份类似 `.gitignore` 的独立读取范围文件；Plugin
  的扫描、索引、缓存、上下文注入和 BYOK 发送都必须遵守它。对 Codex 原生文件工具
  的强制约束能力需要在 Plugin 基座阶段验证并如实说明。
- 交付节奏为先完成正式可用的 Codex Plugin 基座，再依次完整交付 Process Hub、
  Implementation Lens、Prompt Copilot。三个模块均能独立启用和使用，只将其他模块
  视为可选增强来源，不形成业务模块间的硬依赖。
- 初始详细计划见 `plans/001_product_strategy_and_delivery.md`。
- 2026-08-18 已完成阶段一 Codex Plugin 基座：本地 marketplace 安装、Python stdio MCP、
  基座 Skill、生命周期 Hooks、项目级配置与 `.vibesecretaryignore` 统一范围策略均已落地。
  读取范围对 Plugin 自身为强制边界，对 Codex 原生不透明 shell 命令只能提供协作约束，
  不能替代 Codex sandbox 或操作系统权限。
- 2026-08-18 已完成阶段二 Process Hub：consumer project 可以独立配置默认或自定义过程
  collection，并完成非破坏性采用、创建、查询、关系、审阅、生命周期、整理和可重建索引
  闭环。所有修改型能力先预览后显式应用；配置变化会撤销确认。
- 必须区分 VibeSecretary Plugin 开发仓库与使用 Plugin 的 consumer project：开发仓库中
  的 `plans/`、`build_hist/` 只用于研发记录，不应被 Process Hub 当作业务数据扫描、迁移
  或重排；业务测试默认使用独立临时 consumer project。
- 2026-08-19 按用户决定暂缓阶段三，完成阶段四 Prompt Copilot。当前版本只实现 Codex Host，
  BYOK 为明确未实现占位且不会发起网络请求。模块通过单一显式 Skill 和五个 MCP Tools 准备、
  校验带来源的任务包；普通开发 Prompt 主要由 `UserPromptSubmit` 自动工作流处理。schema 2
  新配置默认自动开启和 Review：Quick 静默增强后执行，Review 显示简短摘要后执行，Strict
  当前回合只做完整预检并提供采用优化版、按原文执行、继续优化、取消四个会话选项。
  `strict_blocking` 已删除，Codex Allow 权限框不用于业务选择。仓库上下文是独立基线，
  Process Hub 与 Implementation Lens 仅作可选增强；任一增强不可用时稳定降级。证据摘录遵守范围、预算、
  敏感路径排除和嵌入凭据脱敏。
- Prompt Copilot 的普通 Prompt 入口采用“自动识别 + 单条消息显式覆盖”：开头完整 token
  `@pc` 由 Hook Python 代码强制本次介入，`@npc` 强制本次跳过。显式标记只影响当前消息，
  不建立会话状态；`@pc` 可覆盖 `automatic_enabled = false`，但不能绕过模块总开关。
- 2026-08-19 Process Hub 采用 schema 2 简化 collection 配置：常规只暴露 `id`、`usage`、
  `path`、`path_template`，内部 kind、ID prefix、核心元数据、索引与通用生命周期确定性派生；
  schema 1 保持兼容且不自动迁移。已确认 usage 通过 SessionStart 摘要和 status 完整 catalog
  动态提供给 Codex。工作流明确需要单个过程文档时直接创建；显式只读/预览、实质歧义、
  配置与范围变化、unmanaged 接纳/迁移和批量 organize 继续保留确认。创建 Build History 不
  自动关闭整个 Plan。
- 2026-08-19 已完成阶段三 Implementation Lens。只有消息开头的完整 `@lens` token 会确定性
  拉起该工作流，普通 Prompt 不会触发；用户可在后续文本中指定功能、实现结构、影响方向和
  `module`、`symbol`、`detail` 颗粒度。首版以 Python AST 静态分析为核心，不导入或执行
  consumer project，以源码证据、置信度、诊断和可重建增量索引回答实现问题。默认在项目根
  `ImplementationLens/` 输出配对 Markdown 与自包含离线 HTML 有向 graph，也可通过
  `.vibesecretary/implementation-lens.toml` 配置输出根目录和文件路径模板。Markdown 最后一节
  固定为“只读检查”，用分析前后摘要报告通过、失败或未验证；声明允许的写入仅为模块配置、
  派生索引和用户请求的输出。模块有独立 Skill、六个 MCP Tools 和生命周期，并可作为 Prompt
  Copilot 的可选证据源而不形成硬依赖。
- 2026-08-19 Implementation Lens 运行兼容性修订：输出 `path_template` 与 Process Hub 一样支持
  多级相对目录，并新增 `year`、`month`、`day` 日期变量；`UserPromptSubmit` 的非阻塞上下文在
  Hook bootstrap 边界使用 Codex 官方支持的纯文本 stdout，避免宿主 JSON schema 差异；HTML
  graph 由 Python 预渲染可见首帧 SVG，再由 JavaScript 增强交互，并为无节点和脚本错误提供
  明确状态，不能再把空白画布当作成功结果。
- 2026-08-20 Implementation Lens 的产品目标由“尽可能完整的代码图”调整为“简明、真实的最小充分
  解释”。首次分析在预算内广度建立与 module/symbol/detail 无关的长期派生项目模型，后续依据
  源码摘要和 EvidenceRef 复用或更新；源码始终优先，partial 覆盖与人工修改冲突必须显式呈现。
  单次报告再按认知层级组织有证据的语义 Story，不规定步骤数量，也不向未实现 ReAct 的项目套用
  Think–Act–Observe 模板。默认可视化改为 Markdown + 静态优先 HTML 故事板，原生 details 在无
  JavaScript 时仍可读；用户继续通过 TOML 控制输出根、报告模板和项目模型子目录。
