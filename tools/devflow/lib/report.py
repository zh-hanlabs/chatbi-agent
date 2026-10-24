"""状态快照渲染：把机读状态变成人能直接看的 Markdown 报告。

产出两处：
    .devflow/STATUS.md        每次状态变更后自动重写（CI 与本地都能看）
    docs/STATUS.md            `devflow report --publish` 手动发布到仓库文档区
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from . import gates as G
from . import phases as P
from . import tasks as T
from .state import PHASE_ICON, State

SEVERITY_ICON = {"error": "错误", "warn": "警告", "info": "提示"}


def _phase_table(cfg, state: State) -> str:
    lines = ["| # | 阶段 | 状态 | 进入时间 | 完成时间 | 最近校验 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for phase in P.enabled_phases(cfg):
        info = state.phases().get(phase.id, {})
        status = info.get("status", "pending")
        label = {"pending": "未开始", "active": "进行中", "completed": "已完成",
                 "skipped": "已跳过", "blocked": "受阻"}.get(status, status)
        icon = PHASE_ICON.get(status, "[ ]")
        last = info.get("last_check") or {}
        last_text = "-"
        if last:
            last_text = "%s (%s)" % ("通过" if last.get("ok") else "未通过",
                                     "%dE/%dW" % (last.get("errors") or 0, last.get("warnings") or 0))
        lines.append("| %d | %s %s | %s %s | %s | %s | %s |" % (
            phase.seq, icon, phase.id, label, phase.name,
            (info.get("entered_at") or "-")[:16],
            (info.get("exited_at") or "-")[:16],
            last_text,
        ))
    return "\n".join(lines)


def _gate_section(result: Optional[G.GateResult]) -> str:
    if result is None:
        return "尚未运行过门禁。执行：`devflow gate`"
    lines = [
        "**结论**：%s（错误 %d / 警告 %d / 提示 %d，运行规则 %d 条，模式 `%s`）" % (
            "通过" if result.ok else "未通过",
            len(result.errors), len(result.warns), len(result.infos), len(result.rules_run), result.mode),
        "",
    ]
    if not result.findings:
        lines.append("所有规则均无异常。")
        return "\n".join(lines)
    lines += [
        "| 级别 | 规则 | 问题 | 位置 | 修复建议 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for finding in result.findings:
        lines.append("| %s | `%s` | %s | %s | %s |" % (
            SEVERITY_ICON.get(finding.severity or "", finding.severity or "-"),
            finding.rule,
            finding.message.replace("|", "\\|"),
            (finding.location or "-").replace("|", "\\|"),
            (finding.hint or "-").replace("|", "\\|"),
        ))
    return "\n".join(lines)


def _artifacts_section(state: State) -> str:
    artifacts = state.artifacts()
    if not artifacts:
        return "尚未登记任何交付物。"
    lines = ["| 编号 | 类型 | 标题 | 路径 | 更新时间 |", "| --- | --- | --- | --- | --- |"]
    for item in artifacts:
        lines.append("| %s | %s | %s | `%s` | %s |" % (
            item.get("id", "-"), item.get("kind", "-"), item.get("title", "-"),
            item.get("path", "-"), (item.get("updated_at") or "-")[:16]))
    return "\n".join(lines)


def _task_section(state: State) -> str:
    all_tasks = state.tasks()
    if not all_tasks:
        return "尚未登记任务。"
    stats = T.stats(all_tasks)
    head = [
        "总数 %d ｜ 完成 %d ｜ 进行中 %d ｜ 阻塞 %d ｜ 待办 %d ｜ 逾期 %d" % (
            stats["total"], stats["done"], stats["doing"], stats["blocked"], stats["todo"],
            len(stats["overdue"])),
        "预估工时 %.1fh，已完成 %.1fh（%.1f%%）" % (
            stats["estimate_h"], stats["done_estimate_h"], stats["percent"]),
        "",
    ]
    return "\n".join(head) + "\n" + T.render_table(all_tasks)


def _current_goal(cfg, state: State) -> str:
    pid = state.current_phase()
    phase = P.get_phase(pid)
    if phase is None:
        return "未知阶段 %s" % pid
    lines = ["**%s · %s**：%s" % (phase.seq, phase.name, phase.goal)]
    if phase.next_actions:
        lines.append("")
        lines.append("下一步：")
        for action in phase.next_actions:
            lines.append("- %s" % action)
    return "\n".join(lines)


def render_status(root: str, cfg, state: State, result: Optional[G.GateResult] = None) -> str:
    recent = state.read_log(limit=int(cfg.get("report.recent_events") or 10))
    lines = [
        "# %s 项目管控全景" % cfg.project_name(),
        "",
        "> 本文件由 devflow 自动生成，请勿手工编辑；修改请落到 `devflow.yaml` 与流程命令。",
        "",
        "- 项目：%s" % cfg.project_name(),
        "- 当前阶段：**%s**" % state.current_phase(),
        "- 最近更新：%s" % state.data.get("updated_at", "-"),
        "- 已完成阶段：%s" % ("、".join(state.completed_phases()) or "无"),
        "",
        "## 当前阶段目标",
        "",
        _current_goal(cfg, state),
        "",
        "## 阶段进度",
        "",
        _phase_table(cfg, state),
        "",
        "## 最近一次门禁结果",
        "",
        _gate_section(result),
        "",
        "## 任务与排期",
        "",
        _task_section(state),
        "",
        "## 交付物清单",
        "",
        _artifacts_section(state),
        "",
        "## 最近事件",
        "",
    ]
    if recent:
        lines += ["| 时间 | 事件 | 说明 |", "| --- | --- | --- |"]
        for record in reversed(recent[-10:]):
            payload = {k: v for k, v in record.items() if k not in ("ts", "event")}
            lines.append("| %s | `%s` | %s |" % (
                str(record.get("ts", "-"))[:19].replace("T", " "),
                record.get("event", "-"),
                ", ".join("%s=%s" % (k, v) for k, v in payload.items()) or "-"))
    else:
        lines.append("暂无事件。")
    lines.append("")
    return "\n".join(lines)


def write_status(root: str, cfg, state: State, result: Optional[G.GateResult] = None) -> str:
    rel = str(cfg.get("report.status_file") or ".devflow/STATUS.md")
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_status(root, cfg, state, result))
    return rel


def publish_status(root: str, cfg, state: State, result: Optional[G.GateResult] = None) -> str:
    rel = str(cfg.get("report.publish_to") or "docs/STATUS.md")
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_status(root, cfg, state, result))
    return rel
