"""devflow 命令行入口（argparse 实现，无第三方依赖）。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from . import artifacts as A
from . import ci as CI
from . import contract as C
from . import docs as D
from . import gates as G
from . import phases as P
from . import primitives as PRIM
from . import report as R
from . import tasks as T
from . import config
from .config import load_config, write_config, DEFAULT_CONFIG, dump_yaml  # noqa: F401
from .state import PHASE_STATUS, State, now, today

VERSION = "1.0.0"

# 旧参数名 → 新基线名
PROFILE_ALIASES = {"lite": "minimal", "full": "standard"}

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""SKILL 包根目录（scripts/lib/cli.py → 上三级）。

两种情况都成立：
  * 就地开发：  <skill>/scripts/lib/cli.py      → SKILL_ROOT = <skill>
  * 复制到项目：<project>/tools/devflow/lib/... → SKILL_ROOT = <project>/tools
第二种情况下 `<tools>/templates` 即为模板来源，逻辑依然成立。
"""


def pr(text: str = "") -> None:
    try:
        print(text)
    except UnicodeEncodeError:  # pragma: no cover - 老终端兜底
        print(text.encode("utf-8", "replace").decode(sys.stdout.encoding or "utf-8", "replace"))


def die(message: str, code: int = 2) -> int:
    pr("错误：%s" % message)
    return code


# ------------------------------------------------------------------ 通用
def detect_root(args: argparse.Namespace) -> str:
    # 两种写法都支持：`devflow --root <path> status` 与 `devflow status --root <path>`
    chosen = getattr(args, "root", None) or getattr(args, "root_global", None)
    if chosen:
        return os.path.abspath(chosen)
    return os.path.abspath(os.getcwd())


def require_state(root: str, cfg) -> Optional[State]:
    state = State.load(root, str(cfg.get("paths.state_dir") or ".devflow"))
    if state is None:
        pr("尚未初始化：请先运行 `devflow init`（当前根目录：%s）" % root)
    return state


def _print_findings(result: G.GateResult, verbose: bool = True) -> None:
    icon = {"error": "[ERROR]", "warn": "[WARN ]", "info": "[INFO ]"}
    if not result.findings:
        pr("全部 %d 条规则通过。" % len(result.rules_run))
        return
    order = {"error": 0, "warn": 1, "info": 2}
    for finding in sorted(result.findings, key=lambda f: order.get(f.severity or "", 3)):
        location = "  @ %s" % finding.location if finding.location else ""
        pr("%s %s %s%s" % (icon.get(finding.severity or "", "[?]"), finding.rule, finding.message, location))
        if verbose and finding.hint:
            pr("         → %s" % finding.hint)
    pr("")
    pr("规则 %d 条：错误 %d / 警告 %d / 提示 %d（模式 %s）" % (
        len(result.rules_run), len(result.errors), len(result.warns), len(result.infos), result.mode))
    pr("结论：%s" % ("通过" if result.ok else "未通过"))


def _after_state_change(root: str, cfg, state: State, result: Optional[G.GateResult] = None) -> None:
    state.save()
    if result is not None:
        state.set_last_gate(result.summary())
    R.write_status(root, cfg, state, result)


# ------------------------------------------------------------------ init
def cmd_init(args: argparse.Namespace) -> int:
    root = detect_root(args)
    os.makedirs(root, exist_ok=True)

    cfg_path = os.path.join(root, "devflow.yaml")
    if os.path.exists(cfg_path) and not args.force:
        return die("已存在 devflow.yaml，如需覆盖请加 --force")

    project = {
        "name": args.name or os.path.basename(root),
        "slug": args.slug or "",
        "owner": args.owner or "",
        "repo": args.repo or "",
    }
    profile = PROFILE_ALIASES.get(args.profile, args.profile)
    # 项目配置只写「契约入口 + 项目信息」，阈值与规则一律交给所选基线，
    # 这样基线升级时项目不会用旧快照把新基线覆盖掉。
    probe = config.Config(json.loads(json.dumps(DEFAULT_CONFIG)), root, "default")
    rendered = D.render(
        D.load_template(probe, SKILL_ROOT, root, "project-config.yaml"),
        {"PROFILE": profile, "NAME": project["name"], "SLUG": project["slug"],
         "OWNER": project["owner"], "REPO": project["repo"], "PLATFORM": args.platform},
    )
    config_path = os.path.join(root, "devflow.yaml")
    with open(config_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(rendered)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)

    D.ensure_dirs(root, cfg)
    state_dir = str(cfg.get("paths.state_dir") or ".devflow")
    os.makedirs(os.path.join(root, state_dir), exist_ok=True)

    enabled = [p.id for p in P.enabled_phases(cfg)]
    state = State.create(root, state_dir, project, enabled)
    state.log("init", project=project["name"], platform=args.platform, profile=args.profile)

    tools_rel = str(cfg.get("paths.tools") or "tools/devflow")
    tools_abs = os.path.join(root, tools_rel)
    copied = []
    if not args.no_tools:
        os.makedirs(tools_abs, exist_ok=True)
        source_dir = os.path.join(SKILL_ROOT, "scripts")
        for name in ("devflow.py",):
            shutil.copy2(os.path.join(source_dir, name), os.path.join(tools_abs, name))
            copied.append("%s/%s" % (tools_rel, name))
        lib_target = os.path.join(tools_abs, "lib")
        if os.path.isdir(lib_target):
            shutil.rmtree(lib_target)
        shutil.copytree(os.path.join(source_dir, "lib"), lib_target)
        copied.append("%s/lib/" % tools_rel)
        tmpl_src = os.path.join(SKILL_ROOT, "assets", "templates")
        tmpl_dst = os.path.join(tools_abs, "templates")
        if os.path.isdir(tmpl_src):
            if os.path.isdir(tmpl_dst):
                shutil.rmtree(tmpl_dst)
            shutil.copytree(tmpl_src, tmpl_dst)
            copied.append("%s/templates/" % tools_rel)
        else:
            copied.append("(警告：未发现 assets/templates，自定义类型将使用自动生成的模板)")
        prof_src = os.path.join(SKILL_ROOT, "assets", "profiles")
        prof_dst = os.path.join(tools_abs, "profiles")
        if os.path.isdir(prof_src):
            if os.path.isdir(prof_dst):
                shutil.rmtree(prof_dst)
            shutil.copytree(prof_src, prof_dst)
            copied.append("%s/profiles/" % tools_rel)
        else:
            copied.append("(警告：未发现 assets/profiles，将回退到内置阶段常量)")

    created: List[str] = []

    def _write_if_absent(rel: str, content: str) -> bool:
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            return False
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        return True

    changelog = str(cfg.get("paths.changelog") or "CHANGELOG.md")
    if _write_if_absent(changelog, "# Changelog\n\n"
                                   "本文件遵循 Keep a Changelog 规范，语义化版本号。\n\n"
                                   "## [Unreleased]\n\n- 暂无\n"):
        created.append(changelog)

    if _write_if_absent("README.md", D.render(D.load_template(cfg, SKILL_ROOT, root, "repo-README.md"),
                                              {"PROJECT": cfg.project_name(), "DATE": today(),
                                               "DOCS": cfg.get("paths.docs") or "docs"})):
        created.append("README.md")

    index_rel = "%s/README.md" % (cfg.get("paths.docs") or "docs")
    if not os.path.isfile(os.path.join(root, index_rel)):
        content = D.load_template(cfg, SKILL_ROOT, root, "docs-index.md")
        rendered = D.render(content, {"PROJECT": cfg.project_name(), "DATE": today(),
                                      "DOCS": cfg.get("paths.docs") or "docs",
                                      "PLATFORM": args.platform})
        with open(os.path.join(root, index_rel), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(rendered)
        created.append(index_rel)

    state.save()
    R.write_status(root, cfg, state)

    pr("已初始化 devflow：%s" % root)
    pr("  配置文件：devflow.yaml（基线 %s ｜ 平台 %s ｜ 阶段 %s）" % (
        profile, args.platform, "、".join(enabled)))
    pr("  状态目录：%s/state.json（请随代码提交，进度才能持久化）" % state_dir)
    for item in copied:
        pr("  已复制：%s" % item)
    for item in created:
        pr("  已创建：%s" % item)
    pr("")
    pr("下一步：devflow status  →  devflow new requirement --title \"<需求标题>\"")
    return 0


# ------------------------------------------------------------------ status
def cmd_status(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    if args.json:
        pr(json.dumps({
            "phase": state.current_phase(),
            "phases": state.phases(),
            "tasks": T.stats(state.tasks()),
            "artifacts": state.artifacts(),
        }, ensure_ascii=False, indent=2))
        return 0
    pr("项目：%s" % cfg.project_name())
    pr("当前阶段：%s（%s）" % (state.current_phase(), P.get_phase(state.current_phase()).name
                              if P.get_phase(state.current_phase()) else "未知"))
    pr("")
    pr(R.render_status(root, cfg, state))
    return 0


# ------------------------------------------------------------------ new
def cmd_new(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    try:
        kind = A.resolve_kind(args.kind)
    except KeyError as exc:
        return die(str(exc))
    extra = {}
    for pair in args.set or []:
        if "=" not in pair:
            return die("--set 需要 key=value 形式：%s" % pair)
        key, value = pair.split("=", 1)
        extra[key] = value
    try:
        abs_path, rel, info = D.create_document(
            root, cfg, SKILL_ROOT, kind, args.title, owner=args.owner,
            slug=args.slug, extra=extra, seq_id=args.id or "")
    except FileExistsError as exc:
        return die(str(exc))
    except FileNotFoundError as exc:
        return die(str(exc))

    for key, value in extra.items():
        # 模板里若无对应占位符，则直接落到 front-matter，保证 --set 总能生效
        D.set_front_field(abs_path, key, value)
    state.add_artifact(kind, info["id"], args.title, rel, A.spec(kind).phase)
    D.refresh_index(root, cfg, state)   # 索引自动维护，避免 doc.index 一票否决
    state.log("doc.create", id=info["id"], kind=kind, path=rel)
    if not args.no_status:
        _after_state_change(root, cfg, state)
    pr("已创建：%s" % rel)
    pr("  编号 %s ｜ 类型 %s ｜ 阶段 %s" % (info["id"], kind, A.spec(kind).phase))
    pr("  下一步：按模板填写内容后运行 `devflow check`")
    if A.spec(kind).phase != state.current_phase():
        pr("  提示：该文档属于 %s 阶段，当前阶段是 %s" % (A.spec(kind).phase, state.current_phase()))
    return 0


# ------------------------------------------------------------------ update
def cmd_update(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    record = state.find_artifact(args.target)
    if record is None:
        return die("未登记的交付物：%s（可用 `devflow status` 查看）" % args.target)
    path = os.path.join(root, record["path"])
    changed = []
    for pair in args.set or []:
        if "=" not in pair:
            return die("--set 需要 key=value 形式：%s" % pair)
        key, value = pair.split("=", 1)
        low = value.strip().lower()
        typed: Any
        if low in ("true", "false"):
            typed = low == "true"
        elif low == "null" or low == "":
            typed = None
        elif "," in value and key in ("reviewers", "tags"):
            typed = [v.strip() for v in value.split(",") if v.strip()]
        else:
            typed = value
        if D.set_front_field(path, key, typed):
            changed.append(key)
            state.sync_artifact(args.target)
    if not changed:
        pr("没有字段被更新（文档头部可能不含这些字段）")
        return 0
    state.log("doc.update", id=args.target, fields=",".join(changed))
    _after_state_change(root, cfg, state)
    pr("已更新 %s：%s" % (record["path"], "、".join(changed)))
    return 0


# ------------------------------------------------------------------ check / gate
def _run_check(args: argparse.Namespace, record: bool) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    phase_id = args.phase or state.current_phase()
    scope = args.scope
    result = G.run_gate(root, cfg, state, phase_id, scope, args.mode)
    if record:
        state.set_last_gate(result.summary())
        state.mark_checked(phase_id, result.ok, len(result.errors), len(result.warns))
        state.log("gate.run", phase=phase_id, scope=scope, ok=result.ok,
                  errors=len(result.errors), warnings=len(result.warns))
    state.save()
    R.write_status(root, cfg, state, result)

    if args.json:
        pr(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        phase = P.get_phase(phase_id)
        pr("阶段 %s（%s）｜ %s 检查 ｜ 模式 %s" % (
            phase_id, phase.name if phase else "未知",
            "准入" if scope == "entry" else "准出", result.mode))
        pr("")
        _print_findings(result, verbose=not args.quiet)
    if getattr(args, "all", False):
        pr("")
        pr("提示：`--all` 仅对 `devflow audit` 生效")
    return 0 if result.ok else 1


def cmd_check(args: argparse.Namespace) -> int:
    return _run_check(args, record=True)


def cmd_gate(args: argparse.Namespace) -> int:
    return _run_check(args, record=True)


def cmd_audit(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    result = G.run_all_rules(root, cfg, state, args.phase, args.mode)
    state.log("audit", ok=result.ok, errors=len(result.errors), warnings=len(result.warns))
    state.save()
    if args.json:
        pr(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        pr("全量体检（%d 条规则）｜ 模式 %s" % (len(result.rules_run), result.mode))
        pr("")
        _print_findings(result, verbose=not args.quiet)
    return 0 if result.ok else 1


# ------------------------------------------------------------------ phase
def cmd_phase(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2

    if args.action == "list":
        current = state.current_phase()
        for phase in P.enabled_phases(cfg):
            status = state.phase_status(phase.id)
            mark = {"pending": " ", "active": ">", "completed": "x", "skipped": "-", "blocked": "!"}[status]
            suffix = "  ← 当前" if phase.id == current else ""
            pr("[%s] %d %-8s %-6s %s%s" % (mark, phase.seq, phase.id, phase.name, phase.goal, suffix))
        return 0

    if args.action == "enter":
        target = args.to
        phase = P.get_phase(target)
        if phase is None:
            return die("未知阶段：%s" % target)
        if target not in [p.id for p in P.enabled_phases(cfg)]:
            return die("阶段 %s 在当前配置中未启用" % target)
        merged = G.GateResult(phase=target, scope="transition", mode="graded")
        prev = P.previous_phase(target, cfg)
        prev_checked = False
        if prev is not None and state.phase_status(prev.id) != "skipped":
            prev_checked = True
            prev_result = G.run_gate(root, cfg, state, prev.id, "exit", args.mode)
            for finding in prev_result.findings:
                finding.rule = "[%s/exit] %s" % (prev.id, finding.rule)
            merged.findings.extend(prev_result.findings)
            merged.rules_run.extend(["%s#exit:%s" % (prev.id, r) for r in prev_result.rules_run])
            merged.skipped.extend(prev_result.skipped)
        entry_result = G.run_gate(root, cfg, state, target, "entry", args.mode)
        merged.findings.extend(entry_result.findings)
        merged.rules_run.extend(["%s#entry:%s" % (target, r) for r in entry_result.rules_run])
        merged.skipped.extend(entry_result.skipped)
        merged.mode = entry_result.mode

        if not merged.ok and not args.force:
            if prev_checked:
                pr("不能进入 %s：前置阶段 %s 的准出契约或本阶段准入未通过" % (target, prev.id))
            else:
                pr("不能进入 %s：本阶段准入未通过" % target)
            pr("")
            _print_findings(merged)
            state.mark_checked(target, merged.ok, len(merged.errors), len(merged.warns))
            state.log("phase.enter.blocked", target=target, errors=len(merged.errors))
            state.save()
            R.write_status(root, cfg, state, merged)
            return 1
        if prev is not None and state.phase_status(prev.id) != "completed":
            state.set_phase_status(prev.id, "completed")
        state.set_phase_status(target, "active")
        state.set_current_phase(target)
        state.push_history({"at": now(), "from": prev.id if prev else "", "to": target})
        state.log("phase.enter", target=target,
                  forced=bool(args.force and not merged.ok))
        _after_state_change(root, cfg, state, merged)
        pr("已进入阶段：%s · %s" % (target, phase.name))
        pr("目标：%s" % phase.goal)
        for action in phase.next_actions:
            pr("  - %s" % action)
        return 0

    if args.action == "skip":
        target = args.to
        if target not in [p.id for p in P.enabled_phases(cfg)]:
            return die("阶段 %s 在当前配置中未启用" % target)
        if not args.reason:
            return die("跳过阶段必须给出理由：--reason \"...\"")
        state.set_phase_status(target, "skipped", note=args.reason)
        nxt = P.next_phase(target, cfg)
        if nxt is not None:
            state.set_phase_status(nxt.id, "active")
            state.set_current_phase(nxt.id)
        state.log("phase.skip", target=target, reason=args.reason)
        _after_state_change(root, cfg, state)
        pr("已跳过阶段 %s（理由：%s）" % (target, args.reason))
        return 0

    if args.action == "reset":
        target = args.to or state.current_phase()
        if target not in [p.id for p in P.enabled_phases(cfg)]:
            return die("阶段 %s 在当前配置中未启用" % target)
        # 重做某阶段意味着其下游结论失效，一并回退到 pending（保留 skipped 记录）
        touched = [target]
        cursor = P.next_phase(target, cfg)
        while cursor is not None:
            if state.phase_status(cursor.id) != "skipped":
                state.set_phase_status(cursor.id, "pending")
                touched.append(cursor.id)
            cursor = P.next_phase(cursor.id, cfg)
        state.set_phase_status(target, "pending")
        state.set_current_phase(target)
        state.log("phase.reset", target=target, cascaded=touched[1:])
        _after_state_change(root, cfg, state)
        pr("已重置阶段 %s 为 pending" % target)
        if touched[1:]:
            pr("  下游阶段一并回退：%s（其交付物仍在，重跑 check 即可复用）" % "、".join(touched[1:]))
        return 0

    return die("未知 phase 子命令：%s" % args.action)


# ------------------------------------------------------------------ task
def cmd_task(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    args.id = getattr(args, "target_id", None) or args.id

    if args.action == "add":
        task = T.add(
            state, title=args.title, owner=args.owner or (cfg.get("project.owner") or ""),
            phase=args.phase or "", estimate_h=args.estimate or 0, priority=args.priority,
            tags=args.tag or [], due=args.due or "", start=args.start or "",
            depends_on=args.depends or [], req=args.req or "", note=args.note or "",
            blocking=args.blocking,
        )
        state.log("task.add", id=task["id"], title=task["title"])
        _after_state_change(root, cfg, state)
        pr("已添加任务 %s：%s" % (task["id"], task["title"]))
        missing = []
        for key in ("owner", "estimate_h", "due"):
            if not task.get(key):
                missing.append(key)
        if missing:
            pr("  提醒：仍缺 %s，`devflow check` 会拦截" % "/".join(missing))
        return 0

    if args.action == "list":
        tasks = state.tasks()
        filters: Dict[str, Any] = {}
        if args.status:
            filters["status"] = args.status
        if args.owner:
            filters["owner"] = args.owner
        if args.phase:
            filters["phase"] = args.phase
        tasks = T.filter_tasks(tasks, **filters)
        if not tasks:
            pr("没有匹配的任务。")
            return 0
        pr(T.render_table(tasks))
        pr("")
        stats = T.stats(state.tasks())
        pr("合计 %d 条 ｜ 完成 %d ｜ 逾期 %d ｜ 完成度 %.1f%%" % (
            stats["total"], stats["done"], len(stats["overdue"]), stats["percent"]))
        return 0

    if args.action == "update":
        fields: Dict[str, Any] = {}
        if args.status:
            fields["status"] = args.status
        if args.owner:
            fields["owner"] = args.owner
        if args.estimate is not None:
            fields["estimate_h"] = args.estimate
        if args.due:
            fields["due"] = args.due
        if args.note:
            fields["note"] = args.note
        if args.tag:
            fields["tags"] = args.tag
        if fields.get("status") not in (None, *T.VALID_STATUS):
            return die("非法状态：%s" % args.status)
        try:
            task = T.update(state, args.id, **fields)
        except ValueError as exc:
            return die(str(exc))
        if task is None:
            return die("未找到任务：%s" % args.id)
        state.log("task.update", id=args.id, fields=",".join(fields))
        _after_state_change(root, cfg, state)
        pr("已更新 %s：%s" % (args.id, "、".join("%s=%s" % (k, v) for k, v in fields.items())))
        return 0

    if args.action == "rm":
        before = len(state.tasks())
        state.data["tasks"] = [t for t in state.tasks() if t.get("id", "").lower() != args.id.lower()]
        if len(state.tasks()) == before:
            return die("未找到任务：%s" % args.id)
        state.log("task.remove", id=args.id)
        _after_state_change(root, cfg, state)
        pr("已删除任务 %s" % args.id)
        return 0

    return die("未知 task 子命令：%s" % args.action)


# ------------------------------------------------------------------ approve
def cmd_approve(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    record = state.find_artifact(args.target)
    if record is None:
        return die("未登记的交付物：%s" % args.target)
    art_id = record.get("id")
    existing = [a for a in state.approvals_for(art_id) if a.get("by") == args.by]
    if existing and not args.force:
        return die("%s 已由 %s 评审过（如需覆盖加 --force）" % (art_id, args.by))
    state.add_approval(art_id, args.by, args.role, record.get("phase", ""), args.decision)
    if args.decision == "approved":
        D.set_front_field(os.path.join(root, record["path"]), "status", "approved")
        pr("已登记 %s，并把文档 status 置为 approved" % args.by)
        if D.sync_reviewer(os.path.join(root, record["path"]), args.by):
            pr("     评审人已写入文档头部 reviewers")
    else:
        pr("已登记 %s（%s）" % (args.by, args.decision))
    state.sync_artifact(art_id)
    state.log("approve", target=art_id, by=args.by, role=args.role, decision=args.decision)
    _after_state_change(root, cfg, state)
    pr("评审记录：%s ← %s（%s，%s）" % (art_id, args.by, args.role, args.decision))
    if record.get("phase") and record["phase"] != state.current_phase():
        pr("提示：该交付物属于 %s 阶段" % record["phase"])
    return 0


# ------------------------------------------------------------------ ci
def cmd_ci(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)

    if args.action == "emit":
        try:
            written = CI.emit(root, cfg, SKILL_ROOT, args.platform, args.out, args.overwrite)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            return die(str(exc))
        pr("流水线配置已生成：")
        for rel, status in written.items():
            pr("  %-46s %s" % (rel, status))
        pr("")
        pr("验证方式：本地先跑 `%s gate`，同样的命令会在 CI 里执行。" % (cfg.get("ci.python") or "python3"))
        return 0

    if args.action == "record":
        state = require_state(root, cfg)
        if state is None:
            return 2
        extra = {}
        for pair in args.set or []:
            if "=" not in pair:
                return die("--set 需要 key=value 形式")
            key, value = pair.split("=", 1)
            extra[key] = value
        try:
            data = CI.record_status(root, cfg, args.result, run_id=args.run_id or "", **extra)
        except ValueError as exc:
            return die(str(exc))
        state.log("ci.record", **data)
        state.save()
        pr("已写入 %s：%s" % (cfg.get("ci.status_file"), json.dumps(data, ensure_ascii=False)))
        return 0

    if args.action == "list":
        for name in CI.available_platforms():
            pr("%-8s %s" % (name, CI.PLATFORMS[name]["name"]))
        return 0

    return die("未知 ci 子命令：%s" % args.action)


# ------------------------------------------------------------------ report / log / rules / sync / archive
def cmd_report(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    result = G.run_gate(root, cfg, state, state.current_phase(), "exit")
    rel = R.write_status(root, cfg, state, result)
    published = None
    index = D.refresh_index(root, cfg, state)
    pr("已生成快照：%s" % rel)
    if args.publish:
        published = R.publish_status(root, cfg, state, result)
        pr("已发布到：%s" % published)
    pr("索引已刷新：%s" % (index or "未找到带 devflow:index 标记的索引文件"))
    if index is None:
        pr("提示：在索引文件里加入 <!-- devflow:index:start --> 与 <!-- devflow:index:end --> 标记即可自动维护")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    for record in reversed(state.read_log(limit=args.limit)):
        payload = {k: v for k, v in record.items() if k not in ("ts", "event")}
        pr("%s  %-22s %s" % (str(record.get("ts", ""))[:19].replace("T", " "),
                             record.get("event", ""),
                             json.dumps(payload, ensure_ascii=False) if payload else ""))
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, contract = C.bootstrap(root, SKILL_ROOT)
    rules = G.list_rules()
    if args.json:
        pr(json.dumps([r.__dict__ for r in rules], ensure_ascii=False, indent=2))
        return 0
    disabled = [r for r in contract.rules.values() if not r.enabled]
    pr("| 规则 ID | 级别 | 来源 | 分类 | 说明 |")
    pr("| --- | --- | --- | --- | --- |")
    for rule in rules:
        ref = contract.rule(rule.id)
        level = (ref.severity if ref and ref.severity else rule.severity)
        if ref is not None and not ref.enabled:
            level = "停用"
        pr("| `%s` | %s | %s | %s | %s |" % (
            rule.id, level, rule.source, rule.category, rule.title))
    pr("")
    pr("共 %d 条（内置 %d ／ 自定义 %d ／ 停用 %d）。" % (
        len(rules),
        len([r for r in rules if r.source == "builtin"]),
        len([r for r in rules if r.source != "builtin"]),
        len(disabled)))
    pr("覆盖方式：devflow.yaml#rules（severity / enabled / params / checks）。")
    return 0


# ------------------------------------------------------------------ contract / profile
def cmd_contract(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, contract = C.bootstrap(root, SKILL_ROOT)

    if args.action == "primitives":
        if args.json:
            pr(json.dumps(PRIM.describe(), ensure_ascii=False, indent=2))
        else:
            pr("可用的检查原语（`devflow.yaml#rules[].checks[].type`）：")
            pr("")
            pr("| 原语 | 参数 |")
            pr("| --- | --- |")
            for item in PRIM.describe():
                pr("| `%s` | %s |" % (item["type"], item["params"].replace("|", "\\|")))
            pr("")
            pr("示例：")
            pr("  rules:")
            pr("    - id: custom.no-system-out")
            pr("      title: 禁止调试输出")
            pr("      severity: error")
            pr("      checks:")
            pr("        - type: file_not_contains")
            pr("          glob: \"src/**/*.java\"")
            pr("          pattern: \"System\\\\.out\\\\.println\"")
        return 0

    if args.action == "rules":
        rows = []
        for rid in contract.all_rule_ids():
            ref = contract.rule(rid)
            meta = G._rule_meta(rid)
            rows.append({
                "id": rid,
                "source": (meta.source if meta else ("dsl" if ref and ref.is_dsl else "缺失")),
                "severity": (ref.severity if ref and ref.severity else
                             (meta.severity if meta else "")),
                "enabled": bool(ref.enabled) if ref else True,
                "params": (ref.params if ref else {}),
                "checks": len(ref.checks) if ref else 0,
            })
        if args.json:
            pr(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        pr("| 规则 | 来源 | 级别 | 状态 | 参数 |")
        pr("| --- | --- | --- | --- | --- |")
        for row in rows:
            pr("| `%s` | %s | %s | %s | %s |" % (
                row["id"], row["source"], row["severity"] or "默认",
                "启用" if row["enabled"] else "停用",
                json.dumps(row["params"], ensure_ascii=False) if row["params"] else "-"))
        return 0

    if args.action == "lint":
        notes = contract.validate()
        unknown = contract.unknown_rules()
        for rid in unknown:
            pr("[ERROR] 阶段引用了未定义的规则：%s" % rid)
        for note in notes:
            if note.startswith("阶段") and "未定义的规则" in note:
                continue
            pr("[WARN ] %s" % note)
        if not notes and not unknown:
            pr("契约自检通过：%d 个阶段、%d 种产出物、%d 条规则，无悬空引用。" % (
                len(contract.phases), len(contract.artifacts), len(contract.rules)))
            return 0
        pr("")
        pr("共 %d 个问题。基线链：%s" % (len(notes) + len(unknown), " → ".join(contract.chain) or "(内置常量)"))
        return 1

    if args.action == "export":
        payload = contract.to_dict()
        text = dump_yaml(payload)
        if args.out:
            path = os.path.join(root, args.out)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            pr("已导出生效契约：%s（可作为团队 profile 复用）" % args.out)
        else:
            pr(text)
        return 0

    # show
    if args.json:
        pr(json.dumps(contract.to_dict(), ensure_ascii=False, indent=2))
        return 0
    pr("生效契约：%s" % root)
    pr("基线链：%s" % (" → ".join(contract.chain) or "(内置常量兜底)"))
    pr("")
    pr("## 阶段（%d）" % len(contract.phases))
    pr("")
    pr("| # | 阶段 | 名称 | 产出物 | 准入 | 准出 |")
    pr("| --- | --- | --- | --- | --- | --- |")
    for phase in contract.phases:
        pr("| %s | %s | %s | %s | %d | %d |" % (
            ("%g" % phase.seq), phase.id, phase.name,
            "、".join(phase.artifacts) or "-", len(phase.entry), len(phase.exit)))
    pr("")
    pr("## 产出物类型（%d）" % len(contract.artifacts))
    pr("")
    pr("| 类型 | 编号 | 目录 | 阶段 | 必填字段 | 必填小节 | 模板 |")
    pr("| --- | --- | --- | --- | --- | --- | --- |")
    for kind, spec in contract.artifacts.items():
        pr("| %s | %s-* | `%s` | %s | %d | %d | %s |" % (
            kind, spec.prefix, A.dir_of(root, cfg, kind).replace(root, "").lstrip("\\/") or spec.dir,
            spec.phase or "-", len(spec.required_fields), len(spec.required_sections),
            spec.template or "自动生成"))
    pr("")
    pr("## 规则")
    pr("")
    builtin = len([r for r in G.list_rules() if r.source == "builtin"])
    custom = len([r for r in G.list_rules() if r.source != "builtin"])
    disabled = len([r for r in contract.rules.values() if not r.enabled])
    pr("内置 %d 条 ／ 自定义 %d 条 ／ 停用 %d 条" % (builtin, custom, disabled))
    if contract.notes:
        pr("")
        pr("契约提示：")
        for note in contract.notes:
            pr("  - %s" % note)
    pr("")
    pr("定制入口：`devflow.yaml` 的 phases / artifacts / rules；原语清单 `devflow contract primitives`。")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    pr("内置基线（devflow.yaml#extends 可引用，也可在 .devflow/profiles/ 放同名文件覆盖）：")
    pr("")
    pr("| 基线 | 说明 | 来源 |")
    pr("| --- | --- | --- |")
    for name in C.BUILTIN_PROFILES:
        if name == "none":
            pr("| none | 不继承任何基线，契约完全由项目自行声明 | 内置 |")
            continue
        path = C._find_profile(name, root, cfg, SKILL_ROOT)
        description = ""
        if path:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    description = str(C.yamlmini.loads(fh.read()).get("description") or "")
            except Exception:  # noqa: BLE001 - 基线文件坏掉不应阻断列表展示
                description = ""
        origin = "内置"
        if path:
            origin = "内置" if os.path.abspath(path).startswith(os.path.abspath(SKILL_ROOT)) else "项目覆盖"
        pr("| %s | %s | %s |" % (name, description or "-", origin))
    pr("")
    pr("用法：")
    pr("  devflow init --profile strict")
    pr("  或在 devflow.yaml 写 `extends: [standard, .devflow/profiles/团队基线.yaml]`")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """扫描磁盘上的交付物，回填到状态文件（适合手工建文件或从别处合并的场景）。"""
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    added = 0
    known = {rec.get("path") for rec in state.artifacts()}
    for kind in A.all_kinds():
        for rel in A.list_files(root, cfg, kind):
            if rel in known:
                continue
            info = D.parse_file(os.path.join(root, rel))
            front = info[0]
            art_id = str(front.get("id") or "")
            if not art_id:
                continue
            if state.find_artifact(art_id):
                continue
            state.add_artifact(kind, art_id, str(front.get("title") or ""), rel, A.spec(kind).phase)
            added += 1
    index = D.refresh_index(root, cfg, state)
    state.log("sync", added=added)
    _after_state_change(root, cfg, state)
    pr("已回填 %d 个交付物到状态文件。" % added)
    pr("索引已刷新：%s" % (index or "未找到带 devflow:index 标记的索引文件")) 
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    state = require_state(root, cfg)
    if state is None:
        return 2
    result = G.run_gate(root, cfg, state, state.current_phase(), "exit")
    if not result.ok and not args.force:
        pr("归档前准出未通过：")
        _print_findings(result)
        return 1
    snapshot_dir = os.path.join(root, str(cfg.get("paths.state_dir") or ".devflow"), "archive")
    os.makedirs(snapshot_dir, exist_ok=True)
    name = args.name or today()
    target = os.path.join(snapshot_dir, "%s.json" % name)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(state.data, ensure_ascii=False, indent=2) + "\n")
    state.log("archive", snapshot=os.path.relpath(target, root).replace("\\", "/"))
    _after_state_change(root, cfg, state, result)
    pr("已归档：%s" % os.path.relpath(target, root).replace("\\", "/"))
    pr("如需开启新一轮迭代，可备份后重新 `devflow init --force`。")
    return 0


def cmd_git(args: argparse.Namespace) -> int:
    """辅助：按规范创建分支 / 检查提交格式，减少人工出错。"""
    root = detect_root(args)
    cfg, _contract = C.bootstrap(root, SKILL_ROOT)
    if args.action == "branch":
        if not args.name:
            return die("需要 --name，例如 feature/REQ-001-order-limit")
        patterns = dict(cfg.get("repo.branch_patterns") or {})
        if not any(re.match(p, args.name) for p in patterns.values() if p):
            return die("分支名 `%s` 不匹配任何规范：%s" % (
                args.name, "；".join("%s→%s" % (k, v) for k, v in patterns.items())))
        try:
            proc = subprocess.run(["git", "checkout", "-b", args.name], cwd=root,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError:
            return die("无法执行 git")
        if proc.returncode != 0:
            return die((proc.stderr or "").strip() or "git 执行失败")
        pr("已创建并切换到分支 %s" % args.name)
        return 0
    return die("未知 git 子命令")


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devflow", description="项目全生命周期管控 CLI（八阶段 + 分级门禁 + 状态持久化）")
    parser.add_argument("--version", action="version", version="devflow %s" % VERSION)
    # 顶层 --root：便于 `devflow --root <repo> status` 这种写法
    parser.add_argument("--root", dest="root_global", default=None,
                        help="仓库根目录，默认当前目录；也可写在子命令之后")
    sub = parser.add_subparsers(dest="command")

    # 公共参数
    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--root", help="仓库根目录，默认当前目录")

    # init
    sp = sub.add_parser("init", help="初始化项目管控")
    common(sp)
    sp.add_argument("--name", help="项目名称")
    sp.add_argument("--slug", default="", help="英文标识")
    sp.add_argument("--owner", default="", help="项目负责人")
    sp.add_argument("--repo", default="", help="仓库地址")
    sp.add_argument("--platform", default="github", choices=CI.available_platforms())
    sp.add_argument("--profile", default="standard",
                    choices=["standard", "minimal", "strict", "skeleton", "none", "lite"],
                    help="初始基线：standard=完整实现 / minimal=轻量 / strict=强合规 / "
                         "skeleton=只留框架（lite 为 minimal 的旧别名）")
    sp.add_argument("--no-tools", action="store_true", help="不把运行时复制到仓库")
    sp.add_argument("--force", action="store_true", help="覆盖已有配置")
    sp.set_defaults(func=cmd_init)

    # status
    sp = sub.add_parser("status", help="查看阶段/任务/交付物全景")
    common(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    # new
    sp = sub.add_parser("new", help="按模板创建交付物")
    common(sp)
    sp.add_argument("kind", help="requirement|design|adr|plan|review|test|release|retro")
    sp.add_argument("--title", required=True)
    sp.add_argument("--owner", default="")
    sp.add_argument("--slug", default="", help="文件名后缀，默认从标题生成")
    sp.add_argument("--id", default="", help="指定编号，默认自增")
    sp.add_argument("--set", action="append", metavar="K=V", help="覆盖模板 front-matter 字段，可重复")
    sp.add_argument("--no-status", action="store_true", help="不刷新状态快照")
    sp.set_defaults(func=cmd_new)

    # update
    sp = sub.add_parser("update", help="更新交付物 front-matter 字段")
    common(sp)
    sp.add_argument("target", help="交付物编号，如 REQ-001")
    sp.add_argument("--set", action="append", metavar="K=V", required=True)
    sp.set_defaults(func=cmd_update)

    # check
    sp = sub.add_parser("check", help="校验当前阶段准出契约")
    common(sp)
    sp.add_argument("--phase", help="指定阶段，默认当前阶段")
    sp.add_argument("--scope", default="exit", choices=["exit", "entry"])
    sp.add_argument("--mode", choices=["graded", "strict", "warn", "off"])
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--quiet", action="store_true")
    sp.set_defaults(func=cmd_check)

    # gate
    sp = sub.add_parser("gate", help="跑 CI 门禁（等价于 check，用于流水线）")
    common(sp)
    sp.add_argument("--phase", help="指定阶段，默认当前阶段")
    sp.add_argument("--scope", default="exit", choices=["exit", "entry"])
    sp.add_argument("--mode", choices=["graded", "strict", "warn", "off"])
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--quiet", action="store_true")
    sp.set_defaults(func=cmd_gate)

    # audit
    sp = sub.add_parser("audit", help="全仓库全规则体检")
    common(sp)
    sp.add_argument("--phase", help="指定基线阶段")
    sp.add_argument("--mode", choices=["graded", "strict", "warn", "off"])
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--quiet", action="store_true")
    sp.set_defaults(func=cmd_audit)

    # phase
    sp = sub.add_parser("phase", help="阶段流转")
    common(sp)
    sp.add_argument("action", choices=["list", "enter", "skip", "reset"])
    sp.add_argument("--to", help="目标阶段 id")
    sp.add_argument("--reason", help="跳过阶段的理由")
    sp.add_argument("--mode", choices=["graded", "strict", "warn", "off"])
    sp.add_argument("--force", action="store_true", help="准入未通过也强制进入")
    sp.add_argument("--no-record", action="store_true")
    sp.set_defaults(func=cmd_phase)

    # task
    sp = sub.add_parser("task", help="任务与排期")
    common(sp)
    sp.add_argument("action", choices=["add", "list", "update", "rm"])
    sp.add_argument("target_id", nargs="?", help="任务 ID，例如 T-001（也可写 --id T-001）")
    sp.add_argument("--title")
    sp.add_argument("--id")
    sp.add_argument("--owner")
    sp.add_argument("--phase")
    sp.add_argument("--status", choices=list(T.VALID_STATUS))
    sp.add_argument("--estimate", type=float)
    sp.add_argument("--due")
    sp.add_argument("--start")
    sp.add_argument("--priority", default="P1", choices=["P0", "P1", "P2"])
    sp.add_argument("--tag", action="append", default=[])
    sp.add_argument("--depends", action="append", default=[])
    sp.add_argument("--req", default="")
    sp.add_argument("--note", default="")
    sp.add_argument("--blocking", action="store_true", help="标记为阻塞发布的关键任务")
    sp.set_defaults(func=cmd_task)

    # approve
    sp = sub.add_parser("approve", help="登记评审通过记录")
    common(sp)
    sp.add_argument("--target", required=True, help="交付物编号")
    sp.add_argument("--by", required=True, help="评审人")
    sp.add_argument("--role", default="reviewer")
    sp.add_argument("--decision", default="approved", choices=["approved", "request_changes", "comment"])
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_approve)

    # ci
    sp = sub.add_parser("ci", help="流水线配置与结果回写")
    common(sp)
    sp.add_argument("action", choices=["emit", "record", "list"])
    sp.add_argument("--platform", choices=CI.available_platforms())
    sp.add_argument("--out", default="", help="输出子目录")
    sp.add_argument("--overwrite", action="store_true")
    sp.add_argument("--result", choices=["success", "failed", "cancelled", "running"])
    sp.add_argument("--run-id", default="")
    sp.add_argument("--set", action="append", metavar="K=V")
    sp.set_defaults(func=cmd_ci)

    # report
    sp = sub.add_parser("report", help="生成状态快照")
    common(sp)
    sp.add_argument("--publish", action="store_true", help="同时发布到 docs/STATUS.md")
    sp.set_defaults(func=cmd_report)

    # log
    sp = sub.add_parser("log", help="查看事件日志")
    common(sp)
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_log)

    # rules
    sp = sub.add_parser("rules", help="列出全部门禁规则")
    common(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_rules)

    # contract
    sp = sub.add_parser("contract", help="查看/校验/导出生效契约（阶段、产出物、规则）")
    common(sp)
    sp.add_argument("action", choices=["show", "lint", "export", "rules", "primitives"])
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--out", default="", help="export 的输出路径（相对仓库根）")
    sp.set_defaults(func=cmd_contract)

    # profile
    sp = sub.add_parser("profile", help="列出内置基线与用法")
    common(sp)
    sp.add_argument("action", nargs="?", choices=["list"], default="list")
    sp.set_defaults(func=cmd_profile)

    # sync
    sp = sub.add_parser("sync", help="把磁盘上的交付物回填到状态文件")
    common(sp)
    sp.set_defaults(func=cmd_sync)

    # archive
    sp = sub.add_parser("archive", help="归档当前迭代状态")
    common(sp)
    sp.add_argument("--name", help="归档文件名（不含扩展名）")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_archive)

    # git helper
    sp = sub.add_parser("git", help="分支规范辅助")
    common(sp)
    sp.add_argument("action", choices=["branch"])
    sp.add_argument("--name", help="分支名")
    sp.set_defaults(func=cmd_git)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    if not hasattr(args, "mode"):
        args.mode = None
    if not hasattr(args, "json"):
        args.json = False
    if not hasattr(args, "quiet"):
        args.quiet = False
    if not hasattr(args, "all"):
        args.all = False
    try:
        return int(args.func(args) or 0)
    except SystemExit as exc:
        code = exc.code
        if code is None or code == 0:
            return 0
        if isinstance(code, str):      # SystemExit("可读错误信息")
            pr(code)
            return 1
        return int(code)
