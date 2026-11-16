# Implementation Lens

[English](implementation-lens.md) | [简体中文](implementation-lens_zh.md)

Implementation Lens 使用带证据引用的静态分析解释用户指定的 Python 实现。它追求能够回答问题的最小真实视图，而不是尽可能大的全仓库图。

## 初始化与启用

Foundation 必须已经初始化、确认读取范围并有效启用。在 consumer project 中对 Codex 输入：

```text
使用 $vibe-secretary-implementation-lens 为当前项目初始化 Implementation Lens，先不要启用。
```

审阅 `.vibesecretary/implementation-lens.toml`，然后确认：

```text
我已经审阅 .vibesecretary/implementation-lens.toml，请为当前项目启用 Implementation Lens。
```

Skill 会先调用 `initialize_implementation_lens`，并且只在审阅后调用 `set_implementation_lens_enabled(enabled=true, confirm_config=true)`。之后修改 TOML 会让配置确认失效；继续使用前需要重新审阅并确认。

## 配置

新的 schema 2 配置如下：

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

用户编辑生成文件结构的能力完整保留：

- `output.path` 选择项目内相对输出根目录。
- `output.path_template` 控制配对查询报告的路径，必须包含 `{slug}` 和 `{ext}`，还可以使用 `timestamp`、`granularity`、`language`、`year`、`month` 和 `day`。
- `output.project_model_path` 选择 `output.path` 下的稳定复用模型目录，它不依赖查询颗粒度。
- `index_json` 选择可重建静态索引的位置。

例如：

```toml
[output]
path = "docs/implementation"
path_template = "reports/{year}/{month}/{granularity}/{slug}_{timestamp}.{ext}"
project_model_path = "project-model"
```

路径必须是项目内相对路径且不能包含 `..`。报告不能位于复用模型目录内。修改模板不会自动移动已有报告。

## 开始使用

显式的 `$vibe-secretary-implementation-lens` 名称用于初始化和配置管理。日常分析不需要指定 Skill，只需让当前消息在可选空白之后以完整且不区分大小写的 `@lens` token 开头；默认值不合适时再直接指定认知层级：

```text
@lens 解释这个 Agent 如何规划、调用工具、观察结果并停止，使用 module 颗粒度。
@lens 从 HTTP handler 到持久化跟踪会话续期，使用 symbol 颗粒度。
@lens 展示 token rotation 涉及的分支以及具体读写，使用 detail 颗粒度。
```

`@lensfoo` 或正文中间的 token 不会触发 Lens。只发送 `@lens` 时，Lens 会先询问要分析的实现问题。当前消息一旦命中 Lens 路由，就优先于 Prompt Copilot。

## 颗粒度是认知层级，不是数量指标

- `module` 解释系统的真实职责和概念流程。如果实现确实使用 ReAct，报告可以表达真实的 Think–Act–Observe 循环；Lens 不会把这个模板强套到其他 Agent 或普通项目上。
- `symbol` 从入口到结果跟踪必要组件和关键符号。
- `detail` 展开必要调用、注册、分支、读写和外部边界。

任何层级都不追求固定数量的阶段、符号或关系。节点和边限制只是安全上限。如果省略某个分支、循环、失败路径、边界或不确定性会改变理解，就必须保留；无关邻居会被概括或省略。

## 可复用项目模型与查询报告

回答查询之前，Lens 会检查或更新 `output.path/project_model_path` 下的长期项目模型。它独立于当前报告颗粒度，记录带证据引用的职责、组件、流程、入口和外部边界。后续调用会复用仍然新鲜的记录，并替换已经被源码变化推翻的记录。

大型项目或尚未完整分析的项目会明确标记为 `partial`，同时列出覆盖路径和缺口。源码始终是最高事实来源。受管理模型文件如果被 Lens 之外的工具修改，Lens 会报告冲突而不会静默覆盖。

每次查询会从同一份通过校验的语义 Story 生成配对 Markdown 与离线 HTML。Markdown 包含简明流程、边界、证据附录和只读检查；HTML 是静态优先且可原生展开证据的故事板，JavaScript 只增强展开和筛选。它不会被描述成完整调用图。

## 静态分析与只读边界

分析器使用 Python AST 证据，不导入或执行 consumer code。它可以识别 Python 模块、类、函数、方法、入口、import、常见直接调用、装饰器和注册；反射、动态派发、依赖注入、字符串导入和框架魔法可能只能得到启发式结论或保持未知。

普通 `@lens` 工作流不会修改源码，也不会运行项目入口、测试、构建、格式化或生成器。工具只允许写入配置声明的可重建索引、复用项目模型和配对报告。分析前后会比较源码摘要；`failed` 和 `unverified` 的只读检查绝不会被改写成通过。

## 主要工具

`implementation_lens_status`、`initialize_implementation_lens`、`set_implementation_lens_enabled`、`refresh_implementation_index`、`inspect_implementation_model`、`update_implementation_model`、`query_implementation` 和 `render_implementation_map`。