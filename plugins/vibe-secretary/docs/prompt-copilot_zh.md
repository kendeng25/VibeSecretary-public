# Prompt Copilot

[English](prompt-copilot.md) | [简体中文](prompt-copilot_zh.md)

Prompt Copilot 使用已确认项目范围内的证据增强开发请求，补充任务范围、约束、验收条件和验证建议。自动 Hook 不会替换输入框中的原始消息，也不会偷偷重新提交另一个 Prompt。

## 初始化与启用

Foundation 必须已经初始化、确认读取范围并有效启用。在 consumer project 中对 Codex 输入：

```text
使用 $vibe-secretary-prompt-copilot 为当前项目初始化 Prompt Copilot，先不要启用。
```

审阅 `.vibesecretary/prompt-copilot.toml`，然后确认：

```text
我已经审阅 .vibesecretary/prompt-copilot.toml，请为当前项目启用 Prompt Copilot。
```

Skill 会先调用 `initialize_prompt_copilot`，并且只在审阅后调用 `set_prompt_copilot_enabled(enabled=true, confirm_config=true)`。之后修改 TOML 会让配置确认失效；继续使用前需要重新审阅并确认。

## 配置

新的 schema 2 配置如下：

```toml
schema_version = 2
default_mode = "review"
automatic_enabled = true
context_char_budget = 6000
hook_context_char_budget = 2400
per_source_char_budget = 1000
max_sources = 8
max_scan_files = 500
max_file_bytes = 262144
max_prompt_chars = 16000
```

- `default_mode` 可设为 `quick`、`review` 或 `strict`。
- `automatic_enabled` 只控制普通开发消息。设为 `false` 后，可通过消息开头的 `@pc` 或显式 Skill 按需使用。
- 上下文预算限制证据体量；`hook_context_char_budget` 和 `per_source_char_budget` 都不能超过 `context_char_budget`。
- 扫描与文件限制是安全上限，不表示一定会读取全部匹配文件。

希望减少自动介入时，可以使用以下配置：

```toml
schema_version = 2
default_mode = "quick"
automatic_enabled = false
context_char_budget = 6000
hook_context_char_budget = 2400
per_source_char_budget = 1000
max_sources = 8
max_scan_files = 500
max_file_bytes = 262144
max_prompt_chars = 16000
```

## 模式与控制标记

| 模式 | 自动流程行为 |
|---|---|
| `quick` | 静默融入可靠补充，并在同一回合继续执行任务。 |
| `review` | 先显示简短优化摘要，再在同一回合按增强后的理解继续任务。 |
| `strict` | 只进行不调用工具的完整预检，等待用户选择采用、拒绝、继续修改或取消。 |

消息开头不区分大小写的完整控制 token 只影响当前消息：

```text
@pc 修复 src/auth.py 的会话续期竞态并添加回归测试。
@npc 直接应用已经确认的拼写修复，不运行 Prompt Copilot。
```

- `@pc` 可以在自动检测未命中或 `automatic_enabled=false` 时强制介入，但不能绕过 Foundation、模块总开关、配置确认或 provider 限制。
- `@npc` 强制当前消息跳过 Prompt Copilot。
- token 必须位于可选空白之后的开头并且完整；`@pcc` 或正文中间的 token 不控制路由。
- 单独发送 `@pc` 不会给下一条消息建立状态。

## 开始使用

`$vibe-secretary-prompt-copilot` 主要用于初始化或显式要求完整审阅。启用 `automatic_enabled=true` 后，普通开发消息由 Hook 处理，不需要每次指定 Skill；只有希望强制当前消息介入或跳过时才需要使用开头的 `@pc` 或 `@npc`。

使用默认 `review` 模式时，直接发送普通开发请求：

```text
替换认证缓存，不改变公开 API 行为，并添加回归测试。
```

Prompt Copilot 会先给出简短优化摘要，然后 Codex 在同一回合继续工作。希望显式进行完整审阅而不立即执行时，可以输入：

```text
使用 $vibe-secretary-prompt-copilot 的 strict 模式审阅这个任务：替换认证缓存，不改变公开 API 行为。
```

显式 Skill 审阅会准备并校验带来源的优化包，展示原始理解与优化理解，并等待用户选择采用、修改、使用原文或取消。

## 证据、Provider 与隐私

已确认 `.vibesecretaryignore` 边界内的仓库文件是基础证据。Process Hub 是可选来源。Implementation Lens 可以在显式审阅中提供静态符号证据，但自动 Hook 为控制延迟不会运行 Lens 分析。可选来源缺失时会报告降级，而不会成为硬依赖。

当前只实现 `codex_host`。推理由当前 Codex 会话完成，MCP 工具只负责确定性收集与校验，不会单独发起模型请求。`byok` 是保留但不可用的占位模式。

Prompt Copilot 不会把原始 Prompt、证据摘录或优化 Prompt 写入项目状态或日志。Hook 审计只记录模式、决策、来源数量等运行元数据，所有读取都保持在已确认的项目范围内。

## 主要工具

`prompt_copilot_status`、`initialize_prompt_copilot`、`set_prompt_copilot_enabled`、`prepare_prompt_review` 和 `validate_prompt_package`。