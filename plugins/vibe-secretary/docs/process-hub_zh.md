# Process Hub

[English](process-hub.md) | [简体中文](process-hub_zh.md)

Process Hub 将计划、构建历史、ADR、研究笔记、审阅和自定义过程记录保存为仓库原生 Markdown。Markdown 是事实来源，JSON 和 Markdown 索引属于可重建派生文件。

## 初始化与启用

Foundation 必须已经初始化、确认读取范围并有效启用。在 consumer project 中对 Codex 输入：

```text
使用 $vibe-secretary-process-hub 为当前项目初始化 Process Hub，先不要启用。
```

审阅 `.vibesecretary/process-hub.toml`，然后确认：

```text
我已经审阅 .vibesecretary/process-hub.toml，请为当前项目启用 Process Hub。
```

Skill 会先调用 `initialize_process_hub`，并且只在审阅后调用 `set_process_hub_enabled(enabled=true, confirm_config=true)`。之后修改 TOML 会让配置确认失效；继续使用前需要重新审阅并确认。

## 配置

新的 schema 2 配置只暴露用户真正需要的字段：

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

- `id` 是稳定的 collection 选择标识。
- `usage` 告诉 Codex 什么内容属于该 collection，以及何时创建或维护。
- `path` 是相对 consumer project 根目录的路径。
- `path_template` 控制新文档路径，必须包含 `{id}` 并以 `.md` 结束。

支持的模板变量为 `id`、`slug`、`stage`、`task`、`year`、`month` 和 `day`：

```toml
path_template = "{year}-{month}-{day}/{id}_{slug}.md"
path_template = "{year}/{month}/{id}_{slug}.md"
path_template = "{stage}/{task}/{id}_{slug}.md"
```

collection 目录不能重叠，也不能放在 `.vibesecretary/` 内。模板变化不会自动移动已有文档。内部文档类型、ID 前缀、核心 front matter、默认生命周期和默认索引路径由 Process Hub 派生。

增加自定义 collection 时添加一张表：

```toml
[[collections]]
id = "adr"
usage = "形成影响多个模块的长期架构决策时创建，记录备选方案、取舍和后果。"
path = "docs/adr"
path_template = "{year}/{id}_{slug}.md"
required_metadata = ["owner"]
statuses = ["proposed", "accepted", "superseded", "archived"]
initial_status = "proposed"
terminal_statuses = ["accepted", "superseded", "archived"]
```

`required_metadata` 只填写额外字段；核心字段已经由 Process Hub 管理。

## 开始使用

下面显式写 `$vibe-secretary-process-hub`，适合首次设置、演示或需要强制明确路由的场景，并不表示每个日常请求都必须指定 Skill。按项目调整 consumer [AGENTS.md 范文](agent/AGENTS.md) 后，当项目指令和已确认的 collection `usage` 要求计划、决策、审阅或构建历史时，Codex 可以直接使用 Process Hub。

重大工作前创建计划：

```text
使用 $vibe-secretary-process-hub 为替换认证缓存创建计划，包含范围、设计决策、风险、验收标准和验证方法。
```

实施完成后创建构建历史并关联计划：

```text
使用 $vibe-secretary-process-hub 为认证缓存工作创建构建历史，并关联 PLAN-0001。列出所有修改文件、执行过的检查和剩余限制。
```

查找或审阅记录：

```text
使用 $vibe-secretary-process-hub 查找与认证有关的 active 计划。
使用 $vibe-secretary-process-hub 验证 Process Hub，并报告元数据不一致或关系断裂。
显示 PLAN-0001 及其全部正向和反向关系。
```

安装并按项目调整 consumer [AGENTS.md 范文](agent/AGENTS.md) 后，当已确认的 collection `usage` 要求计划、决策、审阅或构建历史时，普通开发工作也可以自动调用 Process Hub。

## 行为与安全边界

- 当前工作明确需要一个文档时会直接创建，不再重复要求预览确认。
- 只读请求、显式预览、collection 选择有歧义、接纳 unmanaged 文件、配置变化和批量整理仍保留审阅边界。
- `organize_process_documents` 应始终先预览全部移动，再应用。
- 创建构建历史不会自动关闭、归档或移动来源计划。
- 文档不会被覆盖；重复 ID、无效 front matter、路径越界和 collection 重叠都会被拒绝。
- 所有读取和写入都必须位于当前项目及已确认的 `.vibesecretaryignore` 范围内。

## 主要工具

`process_hub_status`、`initialize_process_hub`、`set_process_hub_enabled`、`scan_process_documents`、`query_process_documents`、`get_process_document`、`preview_process_document`、`create_process_document`、`transition_process_document`、`organize_process_documents`、`validate_process_hub` 和 `rebuild_process_index`。
