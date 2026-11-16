"""Static-first HTML storyboards and Markdown reports for Implementation Lens."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from vibe_secretary.implementation_models import (
    EvidenceRef,
    ImplementationStory,
    ImplementationView,
    ReadOnlyCheck,
)
from vibe_secretary.implementation_story import fallback_story


def _relative_href(report_path: Path, project_root: Path, source: str, line: int) -> str:
    target = project_root / Path(source)
    relative = os.path.relpath(target, report_path.parent).replace("\\", "/")
    return f"{relative}#L{line}"


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _evidence_data(
    evidence: EvidenceRef,
    view: ImplementationView,
    report_path: Path,
    project_root: Path,
) -> dict[str, str]:
    nodes = {item.node_id: item for item in view.nodes}
    edges = {item.edge_id: item for item in view.edges}
    if evidence.kind == "node":
        node = nodes.get(evidence.ref_id)
        if node is None:
            return {
                "label": evidence.ref_id,
                "location": "Evidence is outside the query appendix.",
                "href": "",
                "claim": evidence.claim,
                "confidence": "unverified",
            }
        return {
            "label": node.qualified_name,
            "location": f"{node.path}:{node.start_line}",
            "href": _relative_href(report_path, project_root, node.path, node.start_line),
            "claim": evidence.claim,
            "confidence": "certain",
        }
    edge = edges.get(evidence.ref_id)
    if edge is None:
        return {
            "label": evidence.ref_id,
            "location": "Evidence is outside the query appendix.",
            "href": "",
            "claim": evidence.claim,
            "confidence": "unverified",
        }
    return {
        "label": f"{edge.kind}: {edge.source_id} → {edge.target_id}",
        "location": f"{edge.evidence.path}:{edge.evidence.start_line}",
        "href": _relative_href(
            report_path, project_root, edge.evidence.path, edge.evidence.start_line
        ),
        "claim": evidence.claim,
        "confidence": edge.confidence.value,
    }


def _story_or_fallback(
    story: ImplementationStory | None,
    view: ImplementationView,
    title: str,
) -> ImplementationStory:
    return story if story is not None else fallback_story(view, title=title)


def render_markdown(
    *,
    title: str,
    view: ImplementationView,
    read_only: ReadOnlyCheck,
    markdown_path: Path,
    html_path: Path,
    project_root: Path,
    story: ImplementationStory | None = None,
    project_model: dict[str, Any] | None = None,
) -> str:
    """Render an auditable report led by the minimum-sufficient semantic story."""

    selected_story = _story_or_fallback(story, view, title)
    node_by_id = {node.node_id: node for node in view.nodes}
    html_link = os.path.relpath(html_path, markdown_path.parent).replace("\\", "/")
    model = project_model or {}
    lines = [
        f"# {title}",
        "",
        "## 分析请求",
        "",
        f"- 查询：{view.query}",
        f"- 认知层级：`{view.granularity.value}`",
        f"- 语义视图：{len(selected_story.stages)} 个阶段，{len(selected_story.transitions)} 条转换",
        f"- 证据附录：{len(view.nodes)} 个代码节点，{len(view.edges)} 条静态关系",
        f"- 交互报告：[打开 HTML 故事板]({html_link})",
    ]
    if model:
        lines.extend(
            [
                f"- 长期项目模型：`{model.get('status', 'unknown')}` / `{model.get('coverage', 'unknown')}`",
                f"- 项目模型目录：`{model.get('path', '')}`",
            ]
        )
    if selected_story.fallback:
        lines.append("- 展示模式：**证据回退**（未提供语义 Story，不代表完整架构）")
    lines.extend(["", "## 最小充分实现流程", ""])
    for position, stage in enumerate(selected_story.stages, start=1):
        lines.extend(
            [
                f"### {position}. {stage.title}",
                "",
                f"- 角色：`{stage.role}`",
                f"- 性质：`{stage.basis.value}`",
            ]
        )
        if stage.lane:
            lines.append(f"- 泳道：`{stage.lane}`")
        lines.extend(["", stage.summary])
        if stage.details:
            lines.extend(["", "要点：", ""])
            lines.extend(f"- {item}" for item in stage.details)
        lines.extend(["", "证据：", ""])
        if not stage.evidence:
            lines.append("- 无匹配证据；请查看诊断。")
        for evidence in stage.evidence:
            item = _evidence_data(evidence, view, markdown_path, project_root)
            location = (
                f"[{item['location']}]({item['href']})"
                if item["href"]
                else item["location"]
            )
            claim = f" — {item['claim']}" if item["claim"] else ""
            lines.append(
                f"- `{evidence.kind}` `{_escape_markdown(item['label'])}` — "
                f"{location} — `{item['confidence']}`{claim}"
            )
    lines.extend(
        [
            "",
            "## 阶段转换",
            "",
            "| 来源 | 关系 | 目标 | 性质 | 证据 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    stage_by_id = {item.stage_id: item for item in selected_story.stages}
    if not selected_story.transitions:
        lines.append("| — | 当前视图没有声明阶段转换 | — | — | — |")
    for transition in selected_story.transitions:
        evidence_labels = []
        for evidence in transition.evidence:
            item = _evidence_data(evidence, view, markdown_path, project_root)
            evidence_labels.append(f"{evidence.kind}:{_escape_markdown(item['label'])}")
        lines.append(
            "| {source} | {kind}: {label} | {target} | {basis} | {evidence} |".format(
                source=_escape_markdown(stage_by_id[transition.source_id].title),
                kind=transition.kind,
                label=_escape_markdown(transition.label),
                target=_escape_markdown(stage_by_id[transition.target_id].title),
                basis=transition.basis.value,
                evidence="<br>".join(evidence_labels),
            )
        )
    lines.extend(["", "## 选择边界", ""])
    if selected_story.omitted_summary:
        lines.append(selected_story.omitted_summary)
    else:
        lines.append(
            "主视图只保留回答当前问题所需的结构；辅助代码关系位于下方证据附录。"
        )
    lines.extend(
        [
            "",
            "## 代码证据附录",
            "",
            "| 类型 | 符号 | 源码证据 | 入口 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for node in view.nodes:
        href = _relative_href(markdown_path, project_root, node.path, node.start_line)
        lines.append(
            "| {kind} | `{name}` | [{path}:{line}]({href}) | {entry} |".format(
                kind=_escape_markdown(node.kind),
                name=_escape_markdown(node.qualified_name),
                path=_escape_markdown(node.path),
                line=node.start_line,
                href=href,
                entry="是" if node.entrypoint else "否",
            )
        )
    lines.extend(
        [
            "",
            "## 静态关系附录",
            "",
            "| 关系 | 来源 → 目标 | 置信度 | 源码证据 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for edge in view.edges:
        source = node_by_id.get(edge.source_id)
        target = node_by_id.get(edge.target_id)
        if source is None or target is None:
            continue
        href = _relative_href(
            markdown_path, project_root, edge.evidence.path, edge.evidence.start_line
        )
        lines.append(
            "| {kind} | `{source}` → `{target}` | {confidence} | [{path}:{line}]({href}) |".format(
                kind=_escape_markdown(edge.kind),
                source=_escape_markdown(source.qualified_name),
                target=_escape_markdown(target.qualified_name),
                confidence=edge.confidence.value,
                path=_escape_markdown(edge.evidence.path),
                line=edge.evidence.start_line,
                href=href,
            )
        )
    lines.extend(["", "## 局限与诊断", ""])
    limitations = list(dict.fromkeys((*selected_story.limitations, *view.limitations)))
    for limitation in limitations:
        lines.append(f"- {limitation}")
    for diagnostic in view.diagnostics:
        location = f"（{diagnostic.path}:{diagnostic.line}）" if diagnostic.path else ""
        lines.append(f"- `{diagnostic.code}`：{diagnostic.message}{location}")
    if not limitations and not view.diagnostics:
        lines.append("- 无额外诊断。")
    status_labels = {"passed": "通过", "failed": "失败", "unverified": "未验证"}
    lines.extend(
        [
            "",
            "## 只读检查",
            "",
            f"- 结果：**{status_labels.get(read_only.status, read_only.status)}**",
            f"- 方法：{read_only.method}",
            f"- 检查文件数：{read_only.files_checked}",
            "- 允许写入：",
        ]
    )
    for path in read_only.allowed_writes:
        lines.append(f"  - `{path}`")
    lines.append("- 非预期变更：")
    if read_only.unexpected_changes:
        lines.extend(f"  - `{path}`" for path in read_only.unexpected_changes)
    else:
        lines.append("  - 无")
    lines.append("- 验证边界：")
    if read_only.boundaries:
        lines.extend(f"  - {boundary}" for boundary in read_only.boundaries)
    else:
        lines.append(
            "  - 本检查验证了 Implementation Lens 静态分析前后范围内文件内容摘要；"
            "它不声称能够解析或约束 Codex 的不透明 shell 命令。"
        )
    return "\n".join(lines) + "\n"


def _evidence_html(
    evidence: EvidenceRef,
    view: ImplementationView,
    report_path: Path,
    project_root: Path,
) -> str:
    item = _evidence_data(evidence, view, report_path, project_root)
    label = html.escape(item["label"])
    location = html.escape(item["location"])
    claim = f'<p class="claim">{html.escape(item["claim"])}</p>' if item["claim"] else ""
    link = (
        f'<a href="{html.escape(item["href"], quote=True)}">{location}</a>'
        if item["href"]
        else f"<span>{location}</span>"
    )
    return (
        '<li class="evidence-item">'
        f'<code>{html.escape(evidence.kind)}</code> <strong>{label}</strong>'
        f'<span class="confidence">{html.escape(item["confidence"])}</span>'
        f"<div>{link}</div>{claim}</li>"
    )


def render_html_graph(
    *,
    title: str,
    view: ImplementationView,
    html_path: Path,
    project_root: Path,
    story: ImplementationStory | None = None,
    project_model: dict[str, Any] | None = None,
) -> str:
    """Render a self-contained, static-first semantic implementation storyboard."""

    selected_story = _story_or_fallback(story, view, title)
    model = project_model or {}
    safe_title = html.escape(title)
    stages: list[str] = []
    outgoing: dict[str, list[Any]] = {}
    for transition in selected_story.transitions:
        outgoing.setdefault(transition.source_id, []).append(transition)
    stage_by_id = {item.stage_id: item for item in selected_story.stages}
    for position, stage in enumerate(selected_story.stages, start=1):
        details = "".join(f"<li>{html.escape(item)}</li>" for item in stage.details)
        evidence = "".join(
            _evidence_html(item, view, html_path, project_root)
            for item in stage.evidence
        ) or '<li class="evidence-item muted">No matching evidence.</li>'
        transitions = "".join(
            '<li class="transition {kind}"><span>{label}</span> → '
            '<a href="#stage-{target}">{target_title}</a> '
            '<em>{basis}</em></li>'.format(
                kind=html.escape(item.kind),
                label=html.escape(item.label),
                target=html.escape(item.target_id, quote=True),
                target_title=html.escape(stage_by_id[item.target_id].title),
                basis=html.escape(item.basis.value),
            )
            for item in outgoing.get(stage.stage_id, [])
        ) or '<li class="transition muted">No outgoing transition in this view.</li>'
        open_attribute = " open" if position == 1 else ""
        stages.append(
            f'''<details class="stage" id="stage-{html.escape(stage.stage_id, quote=True)}" data-stage-id="{html.escape(stage.stage_id, quote=True)}" data-basis="{html.escape(stage.basis.value, quote=True)}"{open_attribute}>
<summary><span class="step">{position}</span><span class="stage-heading"><small>{html.escape(stage.role)}{(" · " + html.escape(stage.lane)) if stage.lane else ""}</small><strong>{html.escape(stage.title)}</strong></span><span class="basis">{html.escape(stage.basis.value)}</span></summary>
<div class="stage-body"><p>{html.escape(stage.summary)}</p>
{f'<ul class="details">{details}</ul>' if details else ''}
<h3>源码证据</h3><ul class="evidence">{evidence}</ul>
<h3>后续关系</h3><ul class="transitions">{transitions}</ul></div>
</details>'''
        )
    limitation_items = "".join(
        f"<li>{html.escape(item)}</li>"
        for item in dict.fromkeys((*selected_story.limitations, *view.limitations))
    ) or "<li>无额外局限。</li>"
    diagnostic_items = "".join(
        f"<li><code>{html.escape(item.code)}</code> {html.escape(item.message)}</li>"
        for item in view.diagnostics
    ) or "<li>无额外诊断。</li>"
    model_status = html.escape(str(model.get("status", "unknown")))
    model_coverage = html.escape(str(model.get("coverage", "unknown")))
    model_path = html.escape(str(model.get("path", "")))
    omitted = html.escape(
        selected_story.omitted_summary
        or "主视图只保留回答当前问题所需的结构；辅助关系保留在配对 Markdown 中。"
    )
    graph_json = json.dumps(
        selected_story.to_dict(), ensure_ascii=False, separators=(",", ":")
    ).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    fallback_badge = '<span class="warning">证据回退，不是语义全图</span>' if selected_story.fallback else ""
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>
:root {{ color-scheme: light; font-family: Inter, "Segoe UI", system-ui, sans-serif; --ink:#172033; --muted:#667085; --line:#d8dee9; --blue:#245ea8; --paper:#fff; --wash:#f5f7fb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); background:var(--wash); line-height:1.5; }}
a {{ color:var(--blue); }}
header {{ background:#172033; color:#fff; padding:28px clamp(20px,5vw,72px); }}
header h1 {{ margin:0 0 8px; font-size:clamp(24px,4vw,38px); }}
header p {{ margin:0; color:#d7deea; max-width:80ch; }}
.meta {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }}
.meta span,.warning {{ border:1px solid #536078; border-radius:999px; padding:4px 9px; font-size:12px; }}
.warning {{ background:#fff0cf; color:#7a4a00; border-color:#f0b84d; }}
.toolbar {{ position:sticky; top:0; z-index:5; display:flex; flex-wrap:wrap; gap:8px; padding:12px clamp(20px,5vw,72px); background:rgba(255,255,255,.96); border-bottom:1px solid var(--line); }}
button {{ border:1px solid #aeb8c8; border-radius:7px; background:#fff; color:var(--ink); padding:7px 11px; cursor:pointer; }}
button:hover,button:focus-visible {{ border-color:var(--blue); outline:2px solid #b9d6ff; outline-offset:1px; }}
#selection-status {{ margin-left:auto; color:var(--muted); align-self:center; font-size:13px; }}
main {{ width:min(1180px,calc(100% - 32px)); margin:28px auto 64px; }}
.intro,.boundary,.diagnostics {{ background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:18px 20px; margin-bottom:20px; }}
.storyboard {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:20px; align-items:start; }}
.stage {{ position:relative; background:var(--paper); border:1px solid #cbd3df; border-radius:12px; box-shadow:0 5px 18px rgba(30,50,80,.07); overflow:visible; }}
.stage[open] {{ border-color:#6c9bd3; box-shadow:0 8px 24px rgba(36,94,168,.13); }}
.stage summary {{ list-style:none; display:grid; grid-template-columns:auto 1fr auto; gap:12px; align-items:center; cursor:pointer; padding:16px; min-height:82px; }}
.stage summary::-webkit-details-marker {{ display:none; }}
.stage summary:focus-visible {{ outline:3px solid #9bc5ff; outline-offset:-3px; border-radius:11px; }}
.step {{ display:grid; place-items:center; width:34px; height:34px; border-radius:50%; background:#e7f0fc; color:#174d8d; font-weight:700; }}
.stage-heading {{ display:flex; flex-direction:column; min-width:0; }}
.stage-heading small {{ color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
.stage-heading strong {{ overflow-wrap:anywhere; font-size:17px; }}
.basis,.confidence {{ font-size:11px; border-radius:999px; padding:3px 7px; background:#eef2f7; color:#4d596d; }}
.stage-body {{ border-top:1px solid var(--line); padding:2px 16px 18px; }}
.stage-body h3 {{ margin:18px 0 8px; font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:#536078; }}
.details,.evidence,.transitions {{ margin:8px 0 0; padding-left:20px; }}
.evidence-item,.transition {{ margin:8px 0; overflow-wrap:anywhere; }}
.evidence-item .confidence {{ margin-left:7px; }}
.claim {{ margin:3px 0; color:#48566d; }}
.transition.loop {{ color:#7b3f00; }}
.transition.error {{ color:#9d2020; }}
.muted {{ color:var(--muted); }}
.boundary strong {{ display:block; margin-bottom:6px; }}
.diagnostics-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; }}
.diagnostics h2,.intro h2 {{ margin-top:0; }}
@media (max-width:700px) {{
  .storyboard {{ display:block; }} .stage {{ margin-bottom:14px; }}
  .diagnostics-grid {{ grid-template-columns:1fr; }} #selection-status {{ width:100%; margin-left:0; }}
}}
@media print {{ .toolbar {{ display:none; }} body {{ background:#fff; }} main {{ width:100%; }} .stage {{ break-inside:avoid; box-shadow:none; }} }}
</style>
</head>
<body>
<header><h1>{safe_title}</h1><p>{html.escape(view.query)}</p>
<div class="meta"><span>{html.escape(view.granularity.value)}</span><span>{len(selected_story.stages)} 个语义阶段</span><span>项目模型 {model_status}/{model_coverage}</span>{fallback_badge}</div></header>
<div class="toolbar"><button id="expand-all" type="button">展开全部</button><button id="collapse-all" type="button">折叠全部</button><button id="show-all" type="button">显示全部性质</button><button id="show-interpretation" type="button">仅解释性阶段</button><span id="selection-status" role="status" aria-live="polite">首个阶段已展开</span></div>
<main>
<section class="intro"><h2>最小充分实现流程</h2><p>本页优先保证简明与真实，不以展示最多代码实体为目标。每个阶段均可展开查看源码证据。</p>{f'<p>长期项目模型：<code>{model_path}</code></p>' if model_path else ''}</section>
<section class="storyboard" aria-label="Implementation semantic storyboard">{''.join(stages)}</section>
<section class="boundary"><strong>选择边界</strong><span>{omitted}</span></section>
<section class="diagnostics"><div class="diagnostics-grid"><div><h2>局限</h2><ul>{limitation_items}</ul></div><div><h2>诊断</h2><ul>{diagnostic_items}</ul></div></div></section>
</main>
<script>
"use strict";
const story = {graph_json};
const stages = [...document.querySelectorAll("details.stage")];
const status = document.getElementById("selection-status");
function setOpen(value) {{ stages.forEach(stage => {{ stage.open=value; stage.hidden=false; }}); }}
document.getElementById("expand-all").addEventListener("click",()=>{{setOpen(true);status.textContent="已展开全部阶段";}});
document.getElementById("collapse-all").addEventListener("click",()=>{{setOpen(false);status.textContent="已折叠全部阶段";}});
document.getElementById("show-all").addEventListener("click",()=>{{stages.forEach(stage=>stage.hidden=false);status.textContent="已显示全部性质";}});
document.getElementById("show-interpretation").addEventListener("click",()=>{{stages.forEach(stage=>stage.hidden=stage.dataset.basis!=="interpretation");status.textContent="仅显示解释性阶段";}});
stages.forEach(stage=>stage.addEventListener("toggle",()=>{{if(stage.open)status.textContent="已展开："+stage.querySelector("strong").textContent;}}));
</script>
</body>
</html>
'''
