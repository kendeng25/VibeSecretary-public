# VibeSecretary

[English](README.md) | [简体中文](README_zh.md)

VibeSecretary 是一个用于结构化 vibe coding 的本地 Codex 插件。它帮助开发者保存项目上下文、管理开发记录、理解真实实现流程，并把粗略需求整理成更清晰的任务，不需要额外的桌面应用或独立产品 CLI。

<p align="center">
  <img src="figs/vibe-secretary-overview.png" alt="VibeSecretary — Your Vibe Coding Sidekick" width="680">
</p>

## 三项核心功能

### Process Hub

<p align="center">
  <img src="figs/vibe-secretary-process-hub.png" alt="Process Hub — Keep Every Step Organized" width="460">
</p>

Process Hub 将计划、构建历史、ADR、研究笔记、审阅和自定义过程记录保存为仓库原生 Markdown。用户在 TOML 中定义 collection 用途与路径，文档可以由 Git 管理，也支持查找、关联和重建索引。

### Prompt Copilot

<p align="center">
  <img src="figs/vibe-secretary-prompt-copilot.png" alt="Prompt Copilot — Turn Rough Ideas into Clear Prompts" width="460">
</p>

Prompt Copilot 使用已确认的项目证据增强开发请求，补充缺失约束、验收条件和验证建议。它支持自动 Quick、Review、Strict 工作流，也支持通过消息开头的 `@pc` 和 `@npc` 控制当前消息。

### Implementation Lens

<p align="center">
  <img src="figs/vibe-secretary-implementation-lens.png" alt="Implementation Lens — See How Your Code Really Works" width="460">
</p>

Implementation Lens 使用只读 Python 静态分析建立带证据引用的可复用项目模型，并为当前问题生成最小充分解释。消息开头的 `@lens` 会生成配对 Markdown 和静态优先离线 HTML，目标是简明和真实，而不是追求图的绝对完整。

## 本地安装

当前开发工作流使用 Windows PowerShell、Python 3.12 和 Codex CLI。

### 1. 准备运行时

从克隆后的仓库根目录运行：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e plugins\vibe-secretary
python plugins\vibe-secretary\scripts\configure_local_runtime.py
```

最后一条命令会生成 Windows Hooks 使用的运行时描述，并让 MCP 指向仓库本地 `.venv`。移动仓库或重建 `.venv` 后需要重新运行。

### 2. 安装插件

```powershell
$vibeSecretaryRoot = (Resolve-Path .).Path
codex plugin marketplace add $vibeSecretaryRoot
codex plugin add vibe-secretary@personal
codex plugin list --json
```

marketplace 命令只在第一次安装时需要。确认 `vibe-secretary@personal` 已安装并启用。Plugin contribution 会在新的 Codex thread 启动时加载。

### 3. 信任 Hooks 并初始化 Foundation

在 consumer project 中正常启动 Codex：

```powershell
Set-Location D:\path\to\consumer-project
codex
```

运行 `/hooks`，审阅并信任 VibeSecretary Hooks，然后重启一次 Codex。先初始化项目但不启用：

```text
使用 $vibe-secretary-foundation 为当前项目初始化 VibeSecretary，先不要启用。
```

审阅 `.vibesecretary/config.toml` 和 `.vibesecretaryignore`。默认范围会排除常见敏感或无关路径：

```gitignore
.git/
.venv/
.env
refs/
.vibesecretary/cache/
.vibesecretary/logs/
__pycache__/
*.py[cod]
```

然后确认范围并启用 Foundation：

```text
我已经审阅 .vibesecretaryignore，请为当前项目启用 VibeSecretary Foundation 并确认这个读取范围。
```

生成的 Foundation 配置默认关闭，同时保持每个功能独立关闭：

```toml
schema_version = 1
enabled = false
scope_file = ".vibesecretaryignore"

[provider]
mode = "codex_host"
name = ""
api_key_env = ""

[modules.process_hub]
enabled = false
config_file = "process-hub.toml"

[modules.implementation_lens]
enabled = false
config_file = "implementation-lens.toml"

[modules.prompt_copilot]
enabled = false
config_file = "prompt-copilot.toml"
```

不要手工编辑生成的 `scope_digest` 或模块 `config_digest`。修改已确认的范围或功能 TOML 后，只有对应确认会暂时失效；用户重新审阅并确认即可恢复。

需要用项目指令告诉 Codex 何时使用各项功能时，可以复制并调整项目提供的 [consumer project AGENTS.md 范文](plugins/vibe-secretary/docs/agent/AGENTS.md)。

## 配置并开始使用三项功能

每项功能都遵循相同的安全生命周期：初始化、编辑 TOML、明确确认、开始使用。只启用当前项目需要的功能即可。下面在首次配置示例中显式写出 `$skill`，是为了让初始化路由没有歧义；日常工作通常不需要每次指定 Skill。按项目调整 AGENTS.md 范文后，Process Hub 可以依据项目指令和 collection `usage` 使用，Prompt Copilot 可以由自动 Hook 介入，Implementation Lens 只需在消息开头写 `@lens`。

### Process Hub

先初始化但不启用：

```text
使用 $vibe-secretary-process-hub 为当前项目初始化 Process Hub，先不要启用。
```

审阅 `.vibesecretary/process-hub.toml`。默认 schema 2 配置如下：

```toml
schema_version = 2

[[collections]]
id = "plans"
usage = "重大修改前创建计划，记录目标、范围、设计选择和验收条件；实施中按事实维护。"
path = "plans"
path_template = "{year}-{month}-{day}/{id}_{slug}.md"

[[collections]]
id = "build_hist"
usage = "实施和验证结束后创建事实记录，列出实际修改、检查和未完成事项，并在存在来源计划时建立关联。"
path = "build_hist"
path_template = "{year}-{month}-{day}/{id}_{slug}.md"
```

用户可以修改 `path` 和 `path_template`，也可以增加 ADR 等自定义 collection。确认后开始使用：

```text
我已经审阅 .vibesecretary/process-hub.toml，请为当前项目启用 Process Hub。
使用 $vibe-secretary-process-hub 为替换认证缓存创建计划，包含范围、风险、验收标准和验证方法。
```

自定义 collection、路径模板、生命周期操作和更多示例见 [Process Hub 中文文档](plugins/vibe-secretary/docs/process-hub_zh.md)。

### Prompt Copilot

先初始化但不启用：

```text
使用 $vibe-secretary-prompt-copilot 为当前项目初始化 Prompt Copilot，先不要启用。
```

审阅 `.vibesecretary/prompt-copilot.toml`。最重要的配置如下：

```toml
schema_version = 2
default_mode = "review"       # quick、review 或 strict
automatic_enabled = true      # false 表示只通过 @pc 或显式 Skill 按需使用
context_char_budget = 6000
hook_context_char_budget = 2400
per_source_char_budget = 1000
max_sources = 8
max_scan_files = 500
max_file_bytes = 262144
max_prompt_chars = 16000
```

确认后发送普通开发请求，也可以控制单条消息：

```text
我已经审阅 .vibesecretary/prompt-copilot.toml，请为当前项目启用 Prompt Copilot。
替换认证缓存，不改变公开 API 行为，并添加回归测试。
@pc 执行前先审阅并强化这个任务：替换认证缓存。
@npc 直接应用已经确认的拼写修复，不运行 Prompt Copilot。
```

模式行为、路由优先级、证据来源和隐私边界见 [Prompt Copilot 中文文档](plugins/vibe-secretary/docs/prompt-copilot_zh.md)。

### Implementation Lens

先初始化但不启用：

```text
使用 $vibe-secretary-implementation-lens 为当前项目初始化 Implementation Lens，先不要启用。
```

审阅 `.vibesecretary/implementation-lens.toml`。默认 schema 2 布局如下：

```toml
schema_version = 2
default_granularity = "symbol"
index_json = ".vibesecretary/implementation-lens-index.json"

[output]
path = "ImplementationLens"
path_template = "reports/{granularity}/{slug}_{timestamp}.{ext}"
project_model_path = "_project_model"

[limits]
max_files = 2000
max_file_bytes = 1048576
max_nodes = 500
max_edges = 1000
max_audit_files = 5000
```

用户可以编辑输出根目录、报告路径模板和可复用项目模型子目录。确认后使用消息开头的 `@lens` 开始分析：

```text
我已经审阅 .vibesecretary/implementation-lens.toml，请为当前项目启用 Implementation Lens。
@lens 解释这个 Agent 如何规划、调用工具、观察结果并停止，使用 module 颗粒度。
```

`module` 用于职责和概念流程，`symbol` 用于必要符号路径，`detail` 用于证据级调用与分支。它们是认知层级，不对应固定步骤数。复用项目模型、自定义路径、静态分析限制和报告语义见 [Implementation Lens 中文文档](plugins/vibe-secretary/docs/implementation-lens_zh.md)。

## Codex 日常使用

正常启动并加载已安装插件：

```powershell
Set-Location D:\path\to\consumer-project
codex
```

不需要激活 VibeSecretary 环境，也不需要在每个 consumer project 中重复安装插件。希望某次 Codex 进程不加载任何已安装插件时使用：

```powershell
codex --disable plugins
```

`--disable plugins` 会影响当前进程中的全部插件，不会改变全局安装状态。在 consumer project 中停用 VibeSecretary Foundation 会让项目功能失效，但不会从已经运行的 thread 中卸载 Plugin Skills 或 Hooks。

### Sandbox 与授权

推荐的日常命令就是简单的 `codex`。VibeSecretary 不要求无限制文件系统访问权限。

如果完全信任本地项目并且有意扩大 Codex 权限，可以使用以下完整命令：

```powershell
# 使用无限制文件系统权限，并加载 VibeSecretary 和其他已安装插件。
codex --sandbox danger-full-access --ask-for-approval on-request

# 使用相同的宽松 Codex 权限，但不加载任何插件。
codex --sandbox danger-full-access --ask-for-approval on-request --disable plugins
```

这些命令是可选补充，并且会显著降低文件系统隔离。`.vibesecretaryignore` 约束 VibeSecretary 自身的读取和显式路径防护，无法可靠约束不透明 shell 命令、所有形式的 Codex 原生工具或操作系统。需要更强制的边界时，请使用 Codex sandbox 和受管权限。

## 更新、停用或卸载

拉取新版本后，激活 `.venv`、刷新依赖和运行时描述、重新安装当前 marketplace 版本，然后启动新 thread：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e plugins\vibe-secretary
python plugins\vibe-secretary\scripts\configure_local_runtime.py
codex plugin add vibe-secretary@personal
```

可以让 `$vibe-secretary-foundation` 只在当前 consumer project 中停用 VibeSecretary。彻底卸载插件并按需移除本地 marketplace：

```powershell
codex plugin remove vibe-secretary@personal
codex plugin marketplace remove personal
```

只有在没有其他内容依赖 marketplace 时才移除它。卸载插件不会删除项目中已经生成的普通过程文档和报告。

## 文档

- [Process Hub 中文文档](plugins/vibe-secretary/docs/process-hub_zh.md) · [English](plugins/vibe-secretary/docs/process-hub.md)
- [Prompt Copilot 中文文档](plugins/vibe-secretary/docs/prompt-copilot_zh.md) · [English](plugins/vibe-secretary/docs/prompt-copilot.md)
- [Implementation Lens 中文文档](plugins/vibe-secretary/docs/implementation-lens_zh.md) · [English](plugins/vibe-secretary/docs/implementation-lens.md)
- [Consumer project AGENTS.md 范文](plugins/vibe-secretary/docs/agent/AGENTS.md)

## 开发验证

保持 `.venv` 激活，并从仓库根目录运行：

```powershell
$env:PYTHONPATH = (Resolve-Path 'plugins\vibe-secretary\src').Path
python -m pytest plugins\vibe-secretary\tests -q
```