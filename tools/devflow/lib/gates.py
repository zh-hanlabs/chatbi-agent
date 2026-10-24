"""门禁规则引擎。

规则有两类来源，对执行器完全等价：

1. **内置规则**（`builtin`）：本模块用 `@rule` 注册的 Python 实现，覆盖通用工程约束；
2. **DSL 自定义规则**（`dsl`）：项目在契约里用检查原语（见 `primitives.py`）组合而成。

每个阶段在契约里声明自己关心的规则 id（entry / exit），
本模块负责：解析规则 → 逐级求解严重级别 → 分派执行 → 汇总成 GateResult。

严重级别求解顺序（后者覆盖前者）：
    规则自身默认级别（内置规则为 @rule 的 severity，DSL 规则为契约里的 severity）
      → 契约 rules.<id>.severity           项目级覆盖
      → config.gates.mode / phase_modes    阶段模式：strict 全升 error / warn 全降 warn / graded 保持 / off 停用
      → CLI --mode                         临时覆盖
      → Finding.severity                   规则内部针对具体场景的精确定级

契约里 `enabled: false` 或 `mode=off` 的规则直接跳过，不计入 rules_run。
"""

from __future__ import annotations

import glob as globmod
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from . import artifacts as A
from . import docs as D
from . import phases as P
from . import primitives as PRIM
from . import tasks as T
from .contract import get_active
from .model import SEVERITIES, Finding, GateResult, Rule  # noqa: F401 - 兼容旧导入路径
from .state import State

RULES: Dict[str, Rule] = {}
CHECKS: Dict[str, Callable[["Ctx"], List[Finding]]] = {}


def rule(rule_id: str, title: str, category: str, severity: str = "warn", hint: str = ""):
    def decorator(fn: Callable[["Ctx"], List[Finding]]) -> Callable:
        RULES[rule_id] = Rule(rule_id, title, category, severity, hint, source="builtin")
        CHECKS[rule_id] = fn
        return fn
    return decorator


def _resolve_mode(cfg, phase_id: str, override: Optional[str]) -> str:
    if override:
        return override
    return str(cfg.get("gates.phase_modes.%s" % phase_id) or cfg.get("gates.mode") or "graded")


def _rule_ref(cfg, rule_id: str):
    contract = get_active()
    if contract is not None:
        ref = contract.rule(rule_id)
        if ref is not None:
            return ref
    # 无契约时的兜底：直接看旧版 rules.severity / rules.disabled
    override = cfg.get("rules.severity.%s" % rule_id)
    disabled = rule_id in (cfg.get("rules.disabled") or [])
    return _SimpleRef(severity=str(override).lower() if isinstance(override, str) else "",
                      enabled=not disabled, params={}, checks=[], when=[])


class _SimpleRef:
    def __init__(self, severity: str, enabled: bool, params: Dict[str, Any],
                 checks: List[Dict[str, Any]], when: List[Dict[str, Any]]):
        self.severity = severity
        self.enabled = enabled
        self.params = params
        self.checks = checks
        self.when = when


def _resolve_severity(cfg, phase_id: str, rule_id: str, mode: str) -> Optional[str]:
    ref = _rule_ref(cfg, rule_id)
    if ref is not None and not ref.enabled:
        return None
    if rule_id in RULES:
        base = RULES[rule_id].severity
    elif ref is not None and ref.severity:
        base = ref.severity
    else:
        base = "warn"
    if ref is not None and ref.severity in SEVERITIES:
        base = ref.severity
    elif ref is not None and ref.severity == "off":
        return None
    if mode == "off":
        return None
    if mode == "strict":
        return "error"
    if mode == "warn":
        return "warn"
    return base if base in SEVERITIES else "warn"


# ------------------------------------------------------------------ 上下文
class Ctx:
    def __init__(self, root: str, cfg, state: State, phase_id: str, scope: str = "exit"):
        self.root = root
        self.cfg = cfg
        self.state = state
        self.phase_id = phase_id
        self.scope = scope
        self._git_cache: Dict[tuple, tuple] = {}
        self._doc_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._branch: Optional[str] = None

    # ---- git ----
    def git(self, *args: str) -> tuple:
        key = tuple(args)
        if key in self._git_cache:
            return self._git_cache[key]
        try:
            proc = subprocess.run(
                ["git", *args], cwd=self.root, capture_output=True,
                text=True, timeout=30, encoding="utf-8", errors="replace",
            )
            result = (proc.returncode == 0, (proc.stdout or "").strip())
        except Exception:  # noqa: BLE001 - git 不存在或超时都视为不可用
            result = (False, "")
        self._git_cache[key] = result
        return result

    def is_repo(self) -> bool:
        ok, out = self.git("rev-parse", "--is-inside-work-tree")
        return ok and out == "true"

    def branch(self) -> str:
        if self._branch is None:
            ok, out = self.git("rev-parse", "--abbrev-ref", "HEAD")
            self._branch = out if ok else ""
        return self._branch

    # ---- 路径 ----
    def rel(self, path: str) -> str:
        try:
            return os.path.relpath(path, self.root).replace("\\", "/")
        except ValueError:  # pragma: no cover
            return path

    def abs(self, rel: str) -> str:
        return os.path.join(self.root, rel)

    # ---- 文档 ----
    def doc(self, rel: str) -> Optional[Dict[str, Any]]:
        if rel in self._doc_cache:
            return self._doc_cache[rel]
        path = self.abs(rel)
        info: Optional[Dict[str, Any]] = None
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
                front, body = D.parse_text(text)
                info = {"front": front, "body": body, "text": text, "path": rel}
            except (OSError, ValueError):
                info = None
        self._doc_cache[rel] = info
        return info

    def optional_kinds(self) -> List[str]:
        contract = get_active()
        if contract is not None:
            return [k for k, s in contract.artifacts.items() if s.optional]
        return list(self.cfg.get("artifacts.optional") or [])

    def expected_kinds(self) -> List[str]:
        """本轮检查关心的产出物类型（已排除 optional）。"""
        target = self.phase_id
        if self.scope == "entry":
            prev = P.previous_phase(self.phase_id, self.cfg)
            if prev is None:
                return []
            target = prev.id
        return A.required_kinds_of_phase(target, self.cfg)

    # ---- 契约 ----
    @property
    def contract(self):
        return get_active()

    def rule_param(self, rule_id: str, key: str, default: Any = None) -> Any:
        """读取规则参数：优先契约 params，其次返回值 default。"""
        ref = _rule_ref(self.cfg, rule_id)
        if ref is not None and key in ref.params:
            return ref.params[key]
        return default

    # ---- 文件检索（供原语使用）----
    def glob(self, pattern: str) -> List[str]:
        if not pattern:
            return []
        matched = globmod.glob(os.path.join(self.root, pattern), recursive=True)
        result = []
        for path in matched:
            if os.path.isfile(path):
                rel = os.path.relpath(path, self.root).replace("\\", "/")
                if not rel.startswith(".git/"):
                    result.append(rel)
        return sorted(result)

    def artifacts(self, kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """返回 [(kind, rel_path, record)]，磁盘为准，状态登记用于补充元信息。"""
        kinds = kinds if kinds is not None else self.expected_kinds()
        rows: List[Dict[str, Any]] = []
        seen = set()
        records = {(rec.get("path") or ""): rec for rec in self.state.artifacts()}
        for kind in kinds:
            files = A.list_files(self.root, self.cfg, kind)
            extra_paths = [
                p for p, rec in records.items()
                if rec.get("kind") == kind and p not in files and os.path.isfile(self.abs(p))
            ]
            for rel in files + extra_paths:
                if rel in seen:
                    continue
                seen.add(rel)
                rows.append({"kind": kind, "path": rel, "record": records.get(rel)})
        return rows

    def docs(self, kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        result = []
        for row in self.artifacts(kinds):
            info = self.doc(row["path"])
            if info is None:
                continue
            merged = dict(row)
            merged.update(info)
            result.append(merged)
        return result

    def all_docs(self) -> List[Dict[str, Any]]:
        result = []
        for kind in A.all_kinds():
            result.extend(self.docs([kind]))
        return result

    def find_doc(self, rel: str) -> Optional[Dict[str, Any]]:
        info = self.doc(rel)
        if info is None:
            return None
        return dict({"kind": "", "path": rel, "record": None}, **info)


def _tables(text: str) -> List[Dict[str, Any]]:
    """极简 Markdown 表格解析：返回 headers / rows / lineno。"""
    lines = text.split("\n")
    tables: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|?$", lines[i + 1].strip()):
            headers = [c.strip() for c in line.strip("|").split("|")]
            rows: List[tuple] = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                rows.append((j + 1, cells))
                j += 1
            tables.append({"headers": headers, "rows": rows, "lineno": i + 1})
            i = j
            continue
        i += 1
    return tables


def _section_tables(body: str, *sections: str) -> List[Dict[str, Any]]:
    return _tables("\n".join(D.section_text(body, s) for s in sections))


def _col_index(headers: List[str], *names: str) -> Optional[int]:
    """先精确匹配再包含匹配，避免『预期结果』抢占『结果』列。"""
    for i, h in enumerate(headers):
        low = h.strip().lower()
        if low in [n.lower() for n in names]:
            return i
    for i, h in enumerate(headers):
        low = h.lower()
        for name in names:
            if name.lower() in low:
                return i
    return None


def _cell(row: List[str], index: Optional[int]) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


PASS_WORDS = ("通过", "pass", "passed", "ok", "✔", "√")
FAIL_WORDS = ("失败", "fail", "failed", "✘", "×")
NOTRUN_WORDS = ("未执行", "待执行", "-", "", "n/a", "todo", "阻塞", "blocked")


def _result_state(value: str) -> str:
    low = (value or "").strip().lower()
    if low in ("", "-"):
        return "notrun"
    if any(word in low for word in PASS_WORDS):
        return "pass"
    if any(word in low for word in FAIL_WORDS):
        return "fail"
    if low in ("未执行", "待执行", "todo", "阻塞", "blocked", "n/a"):
        return "notrun"
    return "unknown"


# ================================================================= 规则实现
@rule("phase.prev_completed", "未跳过前置阶段", "flow", "error",
      hint="按顺序推进：`devflow check` 让前一阶段准出，再 `devflow phase enter --to <下一阶段>`")
def _r_phase_prev(ctx: Ctx) -> List[Finding]:
    """禁止跳阶段：前序阶段必须处于 active / completed / skipped。

    注意：前一阶段的准出契约由 `phase enter` 单独跑一次（prev 的 exit 规则），
    而不是靠本规则表达，否则会与「把 prev 置为 completed」的时机互相死锁。
    """
    prev = P.previous_phase(ctx.phase_id, ctx.cfg)
    if prev is None:
        return []
    status = ctx.state.phase_status(prev.id)
    if status in ("active", "completed", "skipped"):
        return []
    return [Finding("phase.prev_completed",
                    "前一阶段 %s(%s) 状态为 %s，不允许跳过" % (prev.id, prev.name, status or "未启用"),
                    hint="先让 %s 阶段进入工作状态：`devflow phase enter --to %s`" % (prev.id, prev.id))]


@rule("phase.entry_docs", "上游交付物仍在", "doc", "warn",
      hint="补齐或恢复缺失的文档，或在 devflow.yaml 的 artifacts.optional 中显式豁免")
def _r_phase_entry_docs(ctx: Ctx) -> List[Finding]:
    prev = P.previous_phase(ctx.phase_id, ctx.cfg)
    if prev is None:
        return []
    missing = []
    for kind in prev.artifacts:
        if kind in ctx.optional_kinds():
            continue
        if not A.list_files(ctx.root, ctx.cfg, kind):
            missing.append("%s(%s)" % (kind, A.spec(kind).label))
    if not missing:
        return []
    return [Finding("phase.entry_docs", "上游阶段 %s 的交付物缺失：%s" % (prev.id, "、".join(missing)),
                    hint="`devflow new %s --title \"...\"` 补建，或确认路径配置 devflow.yaml#paths 是否正确" % missing[0].split("(")[0])]


@rule("doc.exists", "本阶段交付物已存在", "doc", "error",
      hint="用 `devflow new <类型> --title \"...\"` 创建")
def _r_doc_exists(ctx: Ctx) -> List[Finding]:
    findings = []
    for kind in ctx.expected_kinds():
        files = A.list_files(ctx.root, ctx.cfg, kind)
        if not files:
            s = A.spec(kind)
            findings.append(Finding(
                "doc.exists", "阶段 %s 缺少产出物：%s（目录 %s）" % (
                    ctx.phase_id, s.label, os.path.relpath(A.dir_of(ctx.root, ctx.cfg, kind), ctx.root).replace("\\", "/")),
                hint="`devflow new %s --title \"<标题>\"` 并按模板填写" % kind))
    return findings


@rule("doc.frontmatter", "front-matter 必填字段齐全", "doc", "error",
      hint="补齐文档头部的 YAML 字段；留空等于没填")
def _r_doc_frontmatter(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs():
        s = A.spec(item["kind"])
        missing = D.empty_fields(item["front"], s.required_fields)
        if missing:
            findings.append(Finding(
                "doc.frontmatter", "%s 缺少必填字段：%s" % (item["path"], "、".join(missing)),
                location=item["path"],
                hint="用 `devflow update %s --set %s=<值>` 或直接编辑文档头部" % (item["front"].get("id", ""), missing[0])))
    return findings


@rule("doc.sections", "正文必填小节齐全", "doc", "warn",
      hint="按模板补全小节，删掉的小节会被视为流程缩水")
def _r_doc_sections(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs():
        s = A.spec(item["kind"])
        missing = D.missing_sections(item["body"], s.required_sections)
        if missing:
            findings.append(Finding(
                "doc.sections", "%s 缺少小节：%s" % (item["path"], "、".join(missing)),
                location=item["path"], hint="对照模板 %s 补全" % s.template))
    return findings


@rule("doc.placeholder", "文档无遗留占位符", "doc", "warn",
      hint="删掉 TODO/TBD 等占位标记（<!-- TODO --> 形式的模板提示不在检查范围内）")
def _r_doc_placeholder(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs():
        hits = D.find_placeholders(item["text"])
        if hits:
            detail = "、".join("第 %d 行 %s" % (lineno, token) for lineno, token in hits[:5])
            findings.append(Finding(
                "doc.placeholder", "%s 仍有占位符：%s" % (item["path"], detail),
                location=item["path"], hint="把占位内容替换为真实结论再提交评审"))
    return findings


@rule("doc.approval", "交付物已获批准", "review", "error",
      hint="在文档中把 status 置为 approved，并登记 reviewers；或用 `devflow approve --target <编号>`")
def _r_doc_approval(ctx: Ctx) -> List[Finding]:
    findings = []
    min_reviewers = int(ctx.rule_param("doc.approval", "min_reviewers",
                                       ctx.cfg.get("review.min_reviewers") or 1))
    for item in ctx.docs():
        front = item["front"]
        status = str(front.get("status", "")).lower()
        art_id = str(front.get("id") or "")
        approvals = ctx.state.approvals_for(art_id)
        approvers = {a.get("by") for a in approvals if a.get("decision") != "request_changes" and a.get("by")}
        reviewers = front.get("reviewers") or front.get("reviewer")
        if isinstance(reviewers, str):
            reviewers = [r.strip() for r in reviewers.split(",") if r.strip()]
        reviewers = set(reviewers or [])
        effective = len(approvers | reviewers)
        if status != "approved":
            findings.append(Finding(
                "doc.approval", "%s 的 status=%s，尚未批准" % (item["path"], status or "空"),
                location=item["path"], hint="评审通过后 `devflow approve --target %s --by <姓名>`" % art_id))
        elif effective < min_reviewers:
            findings.append(Finding(
                "doc.approval", "%s 批准人数不足：%d/%d" % (item["path"], effective, min_reviewers),
                location=item["path"],
                hint="需要至少 %d 名评审人，`devflow approve --target %s --by <姓名>`" % (min_reviewers, art_id)))
    return findings


RECORD_SECTIONS = ("评审记录", "发布记录", "评审")


@rule("doc.review_record", "评审记录可追溯", "review", "warn",
      hint="在『评审记录』小节写明时间、评审人、结论与主要意见")
def _r_doc_review_record(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs():
        found = None
        for name in RECORD_SECTIONS:
            section = D.section_text(item["body"], name)
            if section.strip():
                found = (name, section)
                break
        if found is None:
            # 该类型产出物本就没有评审记录小节（如复盘报告），不做要求
            continue
        clean = D.strip_comments(found[1]).strip()
        if len(clean) < 20:
            findings.append(Finding(
                "doc.review_record", "%s 的『%s』内容过短" % (item["path"], found[0]),
                location=item["path"], hint="至少记录：时间 / 评审人 / 结论 / 主要意见"))
    return findings


@rule("doc.index", "文档索引已更新", "doc", "warn",
      hint="维护 docs/README.md，把新文档路径加进去")
def _r_doc_index(ctx: Ctx) -> List[Finding]:
    docs_root = str(ctx.cfg.get("paths.docs") or "docs")
    candidates = [
        "%s/README.md" % docs_root, "%s/INDEX.md" % docs_root,
        "%s/index.md" % docs_root, "README.md",
    ]
    index_path = None
    content = ""
    for cand in candidates:
        path = ctx.abs(cand)
        if os.path.isfile(path):
            index_path = cand
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            break
    if index_path is None:
        return [Finding("doc.index", "未找到文档索引（%s/README.md）" % docs_root,
                        hint="创建 %s/README.md 并按阶段分类列出所有交付物" % docs_root)]
    missing = []
    for item in ctx.all_docs():
        if item["path"] not in content:
            missing.append(item["path"])
    if not missing:
        return []
    return [Finding("doc.index", "%s 未收录：%s" % (index_path, "、".join(missing[:8])),
                    location=index_path, hint="把上述路径加入索引对应阶段小节")]


@rule("design.contract", "接口与数据契约已定义", "design", "warn",
      hint="至少给出一版接口契约与数据模型，哪怕是草图")
def _r_design_contract(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["design"]):
        for section in ("接口契约", "数据模型"):
            content = D.strip_comments(D.section_text(item["body"], section)).strip()
            content = re.sub(r"^>\s?.*$", "", content, flags=re.M).strip()
            if len(content) < 40:
                findings.append(Finding(
                    "design.contract", "%s 的『%s』内容不足（%d 字）" % (item["path"], section, len(content)),
                    location=item["path"], hint="给出字段/请求响应示例或表结构"))
    return findings


@rule("task.planned", "任务已拆分且字段完整", "plan", "error",
      hint="`devflow task add --title ... --owner ... --estimate 8 --due 2026-11-01`")
def _r_task_planned(ctx: Ctx) -> List[Finding]:
    tasks = ctx.state.tasks()
    if not tasks:
        return [Finding("task.planned", "尚未登记任何任务",
                        hint="先用 `devflow task add` 拆出 WBS")]
    issues = T.unplanned(tasks)
    if not issues:
        return []
    return [Finding("task.planned", "%d 个任务缺少排期字段：%s" % (len(issues), "；".join(issues[:5])),
                    hint="补齐 owner / estimate_h / due 三个字段")]


@rule("task.ownership", "每个任务都有唯一负责人", "plan", "warn",
      hint="`devflow task update <id> --owner <姓名>`")
def _r_task_ownership(ctx: Ctx) -> List[Finding]:
    bad = [t["id"] for t in ctx.state.tasks() if not t.get("owner") and t.get("status") != "cancelled"]
    if not bad:
        return []
    return [Finding("task.ownership", "无负责人的任务：%s" % "、".join(bad))]


@rule("task.schedule", "排期时间合理", "plan", "warn",
      hint="调整 due 日期，或在排期文档中说明重排原因")
def _r_task_schedule(ctx: Ctx) -> List[Finding]:
    plan_docs = ctx.docs(["plan"])
    target = None
    for item in plan_docs:
        target = item["front"].get("target_date")
        if target:
            break
    issues = []
    for task in ctx.state.tasks():
        if task.get("status") in ("done", "cancelled"):
            continue
        # 复盘改进项属于下一迭代，天然会晚于本期目标日，不参与该冲突判定
        if "retro" in (task.get("tags") or []):
            continue
        due = str(task.get("due") or "")
        if target and due and str(due) > str(target):
            issues.append("%s 截止(%s) 晚于计划目标(%s)" % (task["id"], due, target))
    today_str = datetime.now().strftime("%Y-%m-%d")
    if today_str and target and str(target) < today_str:
        issues.append("计划目标日 %s 已过期，需重新排期" % target)
    for task in T.stats(ctx.state.tasks())["overdue"]:
        issues.append("%s 已逾期(due=%s)" % (task["id"], task.get("due")))
    if not issues:
        return []
    return [Finding("task.schedule", "排期冲突：%s" % "；".join(issues[:6]), hint="重排或调整范围")]


@rule("plan.milestones", "里程碑已定义", "plan", "warn",
      hint="在排期文档『里程碑』小节写明关键节点与日期")
def _r_plan_milestones(ctx: Ctx) -> List[Finding]:
    items = ctx.docs(["plan"])
    if not items:
        return []
    findings = []
    date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
    for item in items:
        section = D.strip_comments(D.section_text(item["body"], "里程碑")).strip()
        dates = date_re.findall(section)
        rows = len([line for line in section.split("\n") if line.strip().startswith(("|", "-"))])
        if len(section) < 20 or not dates or rows < 2:
            findings.append(Finding(
                "plan.milestones", "%s 的里程碑未定义或缺少日期" % item["path"],
                location=item["path"], hint="至少给出：方案冻结 / 提测 / 发布 三个节点及日期"))
    return findings


@rule("task.in_progress", "开发任务正在推进", "flow", "warn",
      hint="把正在做的任务标记为 doing：`devflow task update <id> --status doing`")
def _r_task_in_progress(ctx: Ctx) -> List[Finding]:
    tasks = ctx.state.tasks()
    if not tasks:
        return []
    active = [t for t in tasks if t.get("status") in ("doing", "done")]
    blocked = [t for t in tasks if t.get("status") == "blocked" and not t.get("note")]
    findings = []
    if not active:
        findings.append(Finding("task.in_progress", "没有任何任务处于 doing/done，开发与排期脱节"))
    for task in blocked:
        findings.append(Finding("task.in_progress", "任务 %s 被阻塞但未记录原因" % task["id"],
                                hint="`devflow task update %s --note \"阻塞原因\"`" % task["id"]))
    return findings


@rule("task.blocking_done", "阻塞发布的关键任务已完成", "flow", "error",
      hint="要么完成，要么在发布计划里显式降级为已知问题")
def _r_task_blocking(ctx: Ctx) -> List[Finding]:
    pending = T.blocking_open(ctx.state.tasks())
    if not pending:
        return []
    return [Finding("task.blocking_done", "阻塞任务未完成：%s" % "、".join(
        "%s(%s)" % (t["id"], t.get("title")) for t in pending),
        hint="完成后 `devflow task update <id> --status done`")]


@rule("repo.readme", "README 存在", "repo", "warn", hint="补 README.md")
def _r_repo_readme(ctx: Ctx) -> List[Finding]:
    for name in ("README.md", "readme.md", "README.MD"):
        if os.path.isfile(ctx.abs(name)):
            return []
    return [Finding("repo.readme", "仓库缺少 README.md")]


@rule("repo.branch", "分支名符合规范", "repo", "warn",
      hint="按 `feature/<需求号>-<简述>` 或 `fix/<需求号>-<简述>` 建分支")
def _r_repo_branch(ctx: Ctx) -> List[Finding]:
    if not ctx.is_repo():
        return [Finding("repo.branch", "当前目录不是 git 仓库，跳过分支检查", severity="info")]
    branch = ctx.branch()
    if not branch or branch == "HEAD":
        return [Finding("repo.branch", "处于分离 HEAD 状态", hint="新建或切换到一个规范命名的分支")]
    patterns = dict(ctx.rule_param("repo.branch", "patterns",
                                   ctx.cfg.get("repo.branch_patterns") or {}))
    if ctx.scope == "audit":
        # 全量体检没有「当前应在哪个阶段」的语义，只要求分支落在任一规范内
        allowed = [str(ctx.cfg.get("repo.hosting_branch") or "main"),
                   str(ctx.cfg.get("repo.develop_branch") or "develop")]
        if branch in allowed:
            return []
        for pattern in patterns.values():
            if pattern and re.match(pattern, branch):
                return []
        return [Finding("repo.branch", "分支 `%s` 不属于任何规范命名（%s）" % (branch, "、".join(patterns)),
                        hint="`devflow git branch --name feature/<需求号>-<简述>`")]
    expected_groups = {
        "develop": ["feature", "fix"],
        "review": ["feature", "fix"],
        "release": ["release"],
    }.get(ctx.phase_id)
    if not expected_groups:
        return []
    failed = []
    for group in expected_groups:
        pattern = patterns.get(group)
        if not pattern:
            continue
        if re.match(pattern, branch):
            return []
        failed.append("%s 需匹配 %s" % (group, pattern))
    return [Finding("repo.branch", "分支 `%s` 不符合 %s 阶段规范：%s" % (branch, ctx.phase_id, "；".join(failed)),
                    hint="`git checkout -b feature/<需求号>-<简述>`")]


@rule("repo.commit", "提交信息符合约定式提交", "repo", "warn",
      hint="格式：`feat(scope): 简述`，type ∈ %s" % "")
def _r_repo_commit(ctx: Ctx) -> List[Finding]:
    if not ctx.is_repo():
        return [Finding("repo.commit", "当前目录不是 git 仓库，跳过提交检查", severity="info")]
    ok, out = ctx.git("log", "-20", "--format=%s")
    subjects = [line.strip() for line in out.split("\n") if line.strip()]
    if not subjects:
        return [Finding("repo.commit", "仓库还没有任何提交", severity="info")]
    types = list(ctx.rule_param("repo.commit", "types", ctx.cfg.get("repo.commit_types") or []))
    pattern = re.compile(r"^(%s)(\([^)]+\))?!?:\s+.+" % "|".join(re.escape(t) for t in types))
    bad = [s for s in subjects if not s.startswith("Merge ") and not pattern.match(s)]
    if not bad:
        return []
    return [Finding("repo.commit", "最近提交中有 %d 条不符合约定式提交，例如：%s" % (len(bad), bad[0][:60]),
                    hint="规范：`<type>(<scope>): <简述>`，可用 `git commit --amend` 修正最近一条")]


def _walk_files(ctx: Ctx) -> List[str]:
    ignore = list(ctx.cfg.get("repo.ignore_paths") or [])
    results = []
    for dirpath, dirnames, filenames in os.walk(ctx.root):
        rel_dir = os.path.relpath(dirpath, ctx.root).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = [
            d for d in dirnames
            if not any((rel_dir + d + "/").startswith(p.rstrip("/") + "/") or (rel_dir + d + "/") == p for p in ignore)
        ]
        for name in filenames:
            rel = rel_dir + name
            if any(rel.startswith(p.rstrip("/")) for p in ignore):
                continue
            results.append(rel)
    return results


@rule("repo.secrets", "未发现疑似密钥", "security", "error",
      hint="删除明文并用环境变量/密钥管理；确为样例请在 devflow.yaml#repo.ignore_paths 排除")
def _r_repo_secrets(ctx: Ctx) -> List[Finding]:
    patterns = list(ctx.rule_param("repo.secrets", "patterns",
                                   ctx.cfg.get("repo.secret_patterns") or []))
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error:
            continue
    if not compiled:
        return []
    hits: List[Finding] = []
    for rel in _walk_files(ctx):
        path = ctx.abs(rel)
        try:
            if os.path.getsize(path) > 1024 * 1024:
                continue
            with open(path, "rb") as fh:
                raw = fh.read()
            if b"\x00" in raw[:4096]:
                continue
            text = raw.decode("utf-8", errors="ignore")
        except OSError:
            continue
        for index, line in enumerate(text.split("\n"), 1):
            if "devflow.yaml" in rel:
                continue
            for cregex in compiled:
                if cregex.search(line):
                    hits.append(Finding(
                        "repo.secrets", "%s:%d 命中疑似密钥模式" % (rel, index),
                        location="%s:%d" % (rel, index),
                        hint="立即轮转该凭证并改写为环境变量注入"))
                    break
            if len(hits) >= 5:
                return hits
    return hits


@rule("repo.large_files", "无超大文件误入仓库", "repo", "warn", hint="用 Git LFS 或移到构建产物目录并加入 .gitignore")
def _r_repo_large_files(ctx: Ctx) -> List[Finding]:
    limit_mb = float(ctx.rule_param("repo.large_files", "max_mb",
                                    ctx.cfg.get("repo.max_file_mb") or 5))
    if limit_mb <= 0:
        return []
    hits = []
    for rel in _walk_files(ctx):
        try:
            size = os.path.getsize(ctx.abs(rel))
        except OSError:
            continue
        if size > limit_mb * 1024 * 1024:
            hits.append("%s(%.1fMB)" % (rel, size / 1024 / 1024))
    if not hits:
        return []
    return [Finding("repo.large_files", "超过 %.0fMB 的文件 %d 个：%s" % (limit_mb, len(hits), "、".join(hits[:5])),
                    hint="改用 Git LFS 或加入 .gitignore")]


@rule("repo.tree_clean", "工作区无未提交改动", "repo", "warn", hint="提交或 stash 后再跑发布门禁")
def _r_repo_tree_clean(ctx: Ctx) -> List[Finding]:
    if not ctx.is_repo():
        return [Finding("repo.tree_clean", "当前目录不是 git 仓库，跳过", severity="info")]
    ok, out = ctx.git("status", "--porcelain")
    if not ok:
        return []
    # devflow 自身生成的快照属于派生产物，不应算作「未提交的源码改动」
    generated = {
        str(ctx.cfg.get("report.status_file") or ".devflow/STATUS.md"),
        str(ctx.cfg.get("report.publish_to") or "docs/STATUS.md"),
    }
    generated |= set(ctx.cfg.get("repo.clean_ignore") or [])
    changes = []
    for line in out.split("\n"):
        if not line.strip():
            continue
        # porcelain 格式为 `XY PATH`；不同版本对已暂存项的空格处理略有差异，
        # 因此这里统一「去掉两个状态位后左去空格」，而不是按固定偏移量切片。
        path = line[2:].lstrip()
        if " -> " in path:          # 重命名：取新路径
            path = path.split(" -> ", 1)[1]
        candidate = path.strip().strip('"')
        if candidate in generated:
            continue
        changes.append(line.strip())
    if not changes:
        return []
    return [Finding("repo.tree_clean", "有 %d 处未提交改动，例如：%s" % (len(changes), changes[0][:60]),
                    hint="`git add -A && git commit -m \"chore: ...\"`；若某文件是生成产物，"
                         "可加入 devflow.yaml#repo.clean_ignore")]


CI_FILES = {
    "github": [".github/workflows", ".github/workflows/devflow.yml"],
    "gitlab": [".gitlab-ci.yml"],
    "jenkins": ["Jenkinsfile"],
    "cnb": [".cnb.yml"],
}


@rule("ci.config", "流水线配置已纳管", "ci", "warn", hint="`devflow ci emit --platform <平台>` 生成")
def _r_ci_config(ctx: Ctx) -> List[Finding]:
    platform = str(ctx.cfg.get("platform.ci") or "none").lower()
    if platform in ("", "none"):
        return [Finding("ci.config", "devflow.yaml#platform.ci 未设置流水线平台", severity="info")]
    targets = CI_FILES.get(platform, [])
    if not targets:
        return []
    for target in targets:
        if os.path.exists(ctx.abs(target)):
            return []
    return [Finding("ci.config", "未找到 %s 的流水线配置（期望：%s）" % (platform, targets[0]),
                    hint="`devflow ci emit --platform %s`" % platform)]


@rule("ci.last_run", "最近一次流水线成功", "ci", "warn",
      hint="在你的 CI 里加入 `devflow ci record --result success` 步骤")
def _r_ci_last_run(ctx: Ctx) -> List[Finding]:
    rel = str(ctx.cfg.get("ci.status_file") or ".devflow/ci-status.json")
    path = ctx.abs(rel)
    if not os.path.isfile(path):
        return [Finding("ci.last_run", "没有流水线结果记录（%s）" % rel,
                        hint="CI 末尾执行 `devflow ci record --result success` 写入该文件")]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return [Finding("ci.last_run", "%s 无法解析：%s" % (rel, exc))]
    status = str(data.get("status", "")).lower()
    if status not in ("success", "passed", "green"):
        return [Finding("ci.last_run", "最近一次流水线状态为 %s" % (status or "未知"),
                        hint="修复流水线后重新运行 `devflow ci record --result success`")]
    updated = str(data.get("updated_at") or data.get("at") or "")
    if updated:
        try:
            stamp = datetime.fromisoformat(updated.replace("Z", "+00:00").split("+")[0])
            age_days = (datetime.now() - stamp).days
            if age_days > 7:
                return [Finding("ci.last_run", "流水线结果已过期（%d 天前）" % age_days, severity="warn",
                                hint="重新触发流水线刷新 %s" % rel)]
        except ValueError:
            pass
    return []


@rule("review.approvals", "评审通过数达标", "review", "error",
      hint="`devflow approve --target <评审单号> --by <姓名> --role reviewer`")
def _r_review_approvals(ctx: Ctx) -> List[Finding]:
    min_reviewers = int(ctx.rule_param("review.approvals", "min_reviewers",
                                       ctx.cfg.get("review.min_reviewers") or 1))
    findings = []
    for item in ctx.docs(["review"]):
        art_id = str(item["front"].get("id") or "")
        approvers = [a for a in ctx.state.approvals_for(art_id) if a.get("decision") != "request_changes"]
        names = sorted({a.get("by") for a in approvers if a.get("by")})
        reviewers = item["front"].get("reviewers") or []
        if isinstance(reviewers, str):
            reviewers = [r.strip() for r in reviewers.split(",") if r.strip()]
        names = sorted(set(names) | set(reviewers))
        if len(names) < min_reviewers:
            findings.append(Finding(
                "review.approvals", "%s 评审人数 %d/%d" % (item["path"], len(names), min_reviewers),
                location=item["path"], hint="需要至少 %d 名评审人完成 approve" % min_reviewers))
    return findings


@rule("review.checklist", "评审 checklist 已全部勾选", "review", "warn",
      hint="逐项确认后勾选 `- [x]`；不适用的项请写明原因再勾选")
def _r_review_checklist(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["review"]):
        stats = D.checklist_stats(item["body"])
        if stats["total"] == 0:
            findings.append(Finding("review.checklist", "%s 没有 checklist" % item["path"],
                                    location=item["path"], hint="至少覆盖：正确性/边界/安全/性能/可读性/测试"))
        elif stats["unchecked"]:
            findings.append(Finding(
                "review.checklist", "%s 有 %d 项未勾选" % (item["path"], stats["unchecked"]),
                location=item["path"], hint="完成确认后勾选；不适用的写 N/A 并说明"))
    return findings


@rule("review.comments_resolved", "评审意见已闭环", "review", "error",
      hint="把 comments_resolved 置为 true 并清空未闭环意见")
def _r_review_comments(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["review"]):
        value = item["front"].get("comments_resolved")
        unresolved = [ln for ln in D.strip_comments(
            D.section_text(item["body"], "遗留问题与跟进")).split("\n")
            if re.match(r"^\s*[-*]\s+\[\s\]", ln)]
        if value is not True and value != "true":
            findings.append(Finding(
                "review.comments_resolved", "%s 的 comments_resolved 未置为 true" % item["path"],
                location=item["path"],
                hint="`devflow update %s --set comments_resolved=true`" % (item["front"].get("id") or "")))
        elif unresolved:
            findings.append(Finding(
                "review.comments_resolved", "%s 仍有 %d 条未闭环意见" % (item["path"], len(unresolved)),
                location=item["path"]))
    return findings


@rule("test.cases", "测试用例已编写且覆盖分级", "test", "warn",
      hint="至少覆盖：正常流程 / 边界 / 异常三类，并标注优先级")
def _r_test_cases(ctx: Ctx) -> List[Finding]:
    min_cases = int(ctx.rule_param("test.cases", "min_cases", ctx.cfg.get("test.min_cases") or 3))
    findings = []
    for item in ctx.docs(["testplan"]):
        tables = _section_tables(item["body"], "功能用例", "边界与异常用例", "性能与稳定性")
        case_rows = []
        for table in tables:
            prio_idx = _col_index(table["headers"], "优先级", "priority")
            result_idx = _col_index(table["headers"], "结果", "result")
            for lineno, row in table["rows"]:
                if len(row) < 2 or re.match(r"^[-:]+$", row[0] or ""):
                    continue
                case_rows.append((lineno, row, _cell(row, prio_idx), _cell(row, result_idx)))
        if len(case_rows) < min_cases:
            findings.append(Finding(
                "test.cases", "%s 用例数 %d 少于下限 %d" % (item["path"], len(case_rows), min_cases),
                location=item["path"], hint="补齐正常/边界/异常三类用例"))
        if case_rows and not any(cell.strip().upper().startswith("P0") for _, _, cell, _ in case_rows):
            findings.append(Finding(
                "test.cases", "%s 没有标注 P0 用例" % item["path"], location=item["path"],
                hint="至少一条核心路径标为 P0"))
    return findings


@rule("test.results", "P0/P1 用例全部通过", "test", "error",
      hint="执行全部 P0/P1 用例并把『结果』列更新为通过")
def _r_test_results(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["testplan"]):
        tables = _section_tables(item["body"], "功能用例", "边界与异常用例", "性能与稳定性")
        failures: List[str] = []
        notrun: List[str] = []
        for table in tables:
            prio_idx = _col_index(table["headers"], "优先级", "priority")
            result_idx = _col_index(table["headers"], "结果", "result", "执行结果")
            id_idx = _col_index(table["headers"], "用例", "编号", "ID", "id")
            for lineno, row in table["rows"]:
                if len(row) < 2:
                    continue
                prio = _cell(row, prio_idx).strip().upper()
                if not prio.startswith(("P0", "P1")):
                    continue
                state = _result_state(_cell(row, result_idx))
                case_id = _cell(row, id_idx) or "第%d行" % lineno
                if state in ("fail", "unknown"):
                    failures.append(case_id)
                elif state == "notrun":
                    notrun.append(case_id)
        if failures:
            findings.append(Finding("test.results", "%s 有 %d 条 P0/P1 用例未通过：%s" % (
                item["path"], len(failures), "、".join(failures[:6])), location=item["path"],
                hint="修复缺陷后重跑并回填结果"))
        if notrun:
            findings.append(Finding("test.results", "%s 有 %d 条 P0/P1 用例未执行：%s" % (
                item["path"], len(notrun), "、".join(notrun[:6])), location=item["path"],
                hint="执行后把『结果』列填为 通过"))
    return findings


def _read_coverage(ctx: Ctx) -> Optional[float]:
    configured = str(ctx.cfg.get("test.coverage_report") or "").strip()
    candidates = [configured] if configured else []
    candidates += [
        ".devflow/coverage.json", "coverage.json", "coverage/coverage-summary.json",
        "coverage.xml", "target/site/jacoco/jacoco.xml", "build/reports/jacoco/test/jacocoTestReport.xml",
    ]
    for rel in candidates:
        path = ctx.abs(rel)
        if not os.path.isfile(path):
            continue
        try:
            if rel.endswith(".xml"):
                root = ET.parse(path).getroot()
                for attr in ("line-rate", "lines-covered-rate"):
                    if attr in root.attrib:
                        return float(root.attrib[attr]) * 100
                continue
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict):
            for key in ("line_coverage", "coverage", "percent_covered", "line_rate", "percent"):
                if key in data:
                    value = data[key]
                    if isinstance(value, (int, float)):
                        return float(value) * 100 if float(value) <= 1 else float(value)
            totals = data.get("totals")
            if isinstance(totals, dict):
                for key in ("percent_covered", "line_coverage", "covered_lines_percent"):
                    if key in totals and isinstance(totals[key], (int, float)):
                        return float(totals[key])
    return None


@rule("test.coverage", "测试覆盖率达标", "test", "warn",
      hint="产出覆盖率报告（coverage.json / coverage.xml）并达到阈值")
def _r_test_coverage(ctx: Ctx) -> List[Finding]:
    threshold = float(ctx.rule_param("test.coverage", "min", ctx.cfg.get("test.min_coverage") or 0))
    value = _read_coverage(ctx)
    if value is None:
        return [Finding("test.coverage", "未读取到覆盖率数据",
                        hint="测试阶段产出 .devflow/coverage.json（{\"line_coverage\": 82.5}）或 coverage.xml")]
    if value < threshold:
        return [Finding("test.coverage", "覆盖率 %.1f%% 低于阈值 %.1f%%" % (value, threshold),
                        hint="补充单测/集成测试覆盖核心分支")]
    return []


@rule("test.bug_triage", "高优先级缺陷已清零", "test", "error",
      hint="修复 P0/blocker 缺陷后再放行；无法修复需在发布计划中登记为已知问题")
def _r_test_bug_triage(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["testplan"]):
        tables = _section_tables(item["body"], "缺陷跟踪")
        if not tables:
            findings.append(Finding("test.bug_triage", "%s 未登记缺陷跟踪表" % item["path"],
                                    location=item["path"], hint="没有缺陷就写一行「无」；有则逐条登记状态"))
            continue
        open_bugs: List[str] = []
        for table in tables:
            sev_idx = _col_index(table["headers"], "严重", "级别", "优先级", "severity", "priority")
            state_idx = _col_index(table["headers"], "状态", "status")
            id_idx = _col_index(table["headers"], "缺陷", "编号", "ID", "id")
            for lineno, row in table["rows"]:
                if len(row) < 2:
                    continue
                if all(not cell or re.match(r"^[-:]+$", cell) for cell in row):
                    continue
                severity = _cell(row, sev_idx).upper()
                status = _cell(row, state_idx).strip()
                bug_id = _cell(row, id_idx) or "第%d行" % lineno
                if severity.startswith(("P0", "BLOCKER", "S1", "致命", "严重")) and status not in (
                        "已修复", "已关闭", "closed", "fixed", "resolved", "wontfix", "已忽略"):
                    open_bugs.append(bug_id)
        if open_bugs:
            findings.append(Finding("test.bug_triage", "%s 存在未闭环高优先级缺陷：%s" % (
                item["path"], "、".join(open_bugs[:6])), location=item["path"],
                hint="修复并复测，或走例外审批写入发布计划"))
    return findings


@rule("release.changelog", "CHANGELOG 已更新", "release", "error",
      hint="在 CHANGELOG.md 顶部写入本次版本号、日期与变更摘要")
def _r_release_changelog(ctx: Ctx) -> List[Finding]:
    rel = str(ctx.cfg.get("paths.changelog") or "CHANGELOG.md")
    path = ctx.abs(rel)
    if not os.path.isfile(path):
        return [Finding("release.changelog", "缺少 %s" % rel)]
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    if len(D.strip_comments(content).strip()) < 20:
        return [Finding("release.changelog", "%s 为空" % rel)]
    findings = []
    for item in ctx.docs(["releaseplan"]):
        version = str(item["front"].get("version") or "").strip()
        if version and version not in content:
            findings.append(Finding("release.changelog", "%s 未记录版本 %s" % (rel, version),
                                    location=rel, hint="按 Keep a Changelog 格式追加"))
    return findings


@rule("release.version", "版本号与 tag 一致", "release", "error",
      hint="补齐 version 字段并打 tag：`git tag vX.Y.Z && git push --tags`")
def _r_release_version(ctx: Ctx) -> List[Finding]:
    findings = []
    prefix = str(ctx.rule_param("release.version", "tag_prefix",
                                ctx.cfg.get("release.tag_prefix") or "v"))
    require_tag = bool(ctx.rule_param("release.version", "require_tag",
                                      ctx.cfg.get("release.require_tag", True)))
    tags_ok, tags_out = ctx.git("tag", "--list") if ctx.is_repo() else (False, "")
    tags = tags_out.split("\n") if tags_ok else []
    for item in ctx.docs(["releaseplan"]):
        version = str(item["front"].get("version") or "").strip()
        if not version:
            findings.append(Finding("release.version", "%s 缺少 version 字段" % item["path"],
                                    location=item["path"],
                                    hint="`devflow update %s --set version=1.2.0`" % (item["front"].get("id") or "")))
            continue
        tag = version if version.startswith(prefix) else prefix + version.lstrip("v")
        if require_tag and ctx.is_repo() and tag not in tags:
            findings.append(Finding("release.version", "版本 %s 对应的 tag %s 不存在" % (version, tag),
                                    location=item["path"], hint="`git tag %s && git push --tags`" % tag))
    return findings


@rule("release.rollback", "回滚方案可用", "release", "error",
      hint="写明触发条件、回滚步骤、数据兼容处理与验证方式")
def _r_release_rollback(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["releaseplan"]):
        ready = item["front"].get("rollback_ready")
        section = D.strip_comments(D.section_text(item["body"], "回滚方案"))
        section = re.sub(r"^>\s?.*$", "", section, flags=re.M).strip()
        if len(section) < 40:
            findings.append(Finding("release.rollback", "%s 的『回滚方案』内容不足" % item["path"],
                                    location=item["path"], hint="至少写清：触发条件 / 步骤 / 数据回滚 / 验证"))
        if ready is not True and ready != "true":
            findings.append(Finding("release.rollback", "%s 的 rollback_ready 未置为 true" % item["path"],
                                    location=item["path"],
                                    hint="`devflow update %s --set rollback_ready=true`" % (item["front"].get("id") or "")))
    return findings


@rule("release.env_ready", "发布环境就绪", "release", "error",
      hint="核对配置、灰度策略与权限后把 env_ready 置为 true")
def _r_release_env(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["releaseplan"]):
        ready = item["front"].get("env_ready")
        if ready is not True and ready != "true":
            findings.append(Finding("release.env_ready", "%s 的 env_ready 未置为 true" % item["path"],
                                    location=item["path"],
                                    hint="`devflow update %s --set env_ready=true`" % (item["front"].get("id") or "")))
    return findings


@rule("retro.metrics", "复盘指标已量化", "retro", "warn",
      hint="用数据说话：需求交付周期、缺陷密度、返工率、覆盖率等")
def _r_retro_metrics(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["retro"]):
        section = D.strip_comments(D.section_text(item["body"], "指标回顾"))
        section = re.sub(r"^>\s?.*$", "", section, flags=re.M).strip()
        numbers = re.findall(r"\d+(\.\d+)?%?|\d+", section)
        if len(section) < 40 or len(numbers) < 2:
            findings.append(Finding("retro.metrics", "%s 的『指标回顾』缺少量化数据" % item["path"],
                                    location=item["path"], hint="至少给出 2 项可对比的数值指标"))
    return findings


@rule("retro.actions", "改进项有负责人", "retro", "warn",
      hint="每条改进项写成 `- [ ] 动作 —— @负责人，截止 YYYY-MM-DD`")
def _r_retro_actions(ctx: Ctx) -> List[Finding]:
    findings = []
    for item in ctx.docs(["retro"]):
        section = D.strip_comments(D.section_text(item["body"], "待改进项"))
        items = [ln.strip() for ln in section.split("\n") if re.match(r"^\s*[-*]\s+", ln)]
        if not items:
            findings.append(Finding("retro.actions", "%s 没有登记改进项" % item["path"],
                                    location=item["path"], hint="至少给出 1 条可执行改进项"))
            continue
        no_owner = [ln for ln in items if "@" not in ln]
        if no_owner:
            findings.append(Finding("retro.actions", "%s 有 %d 条改进项缺少 @负责人" % (item["path"], len(no_owner)),
                                    location=item["path"], hint="补充负责人与截止时间"))
    return findings


# ================================================================= 执行入口
def collect_rules(phase_id: str, scope: str, cfg) -> List[str]:
    """取某阶段该跑哪些规则：来自契约，内置与 DSL 一视同仁。"""
    contract = get_active()
    if contract is not None:
        return contract.rule_ids_for(phase_id, scope)
    phase = P.get_phase(phase_id)
    if phase is None:
        return []
    ids = list(phase.entry_rules) if scope == "entry" else list(phase.exit_rules)
    return [rid for rid in ids if rid in CHECKS]


def _rule_meta(rule_id: str) -> Optional[Rule]:
    """规则元信息：内置规则取 RULES，DSL 规则由契约合成。"""
    if rule_id in RULES:
        return RULES[rule_id]
    contract = get_active()
    ref = contract.rule(rule_id) if contract is not None else None
    if ref is None or not ref.is_dsl:
        return None
    return Rule(id=ref.id, title=ref.title or ref.id, category=ref.category,
                severity=ref.severity or "warn", source="dsl")


def _run_dsl(ctx: Ctx, rule_id: str) -> List[Finding]:
    ref = _rule_ref(ctx.cfg, rule_id)
    if ref is None or not ref.checks:
        return []
    if ref.when:
        # 前置条件：全部通过才执行本体
        blockers = PRIM.run_all(ctx, ref.when, rule_id)
        if blockers:
            return []
    return PRIM.run_all(ctx, ref.checks, rule_id)


def run_rules(ctx: Ctx, rule_ids: List[str], mode: str) -> GateResult:
    result = GateResult(phase=ctx.phase_id, scope=ctx.scope, mode=mode)
    for rule_id in rule_ids:
        meta = _rule_meta(rule_id)
        if meta is None:
            result.skipped.append(rule_id)
            continue
        severity = _resolve_severity(ctx.cfg, ctx.phase_id, rule_id, mode)
        if severity is None:
            result.skipped.append(rule_id)
            continue
        result.rules_run.append(rule_id)
        try:
            if meta.source == "dsl":
                findings = _run_dsl(ctx, rule_id)
            else:
                findings = CHECKS[rule_id](ctx) or []
        except Exception as exc:  # noqa: BLE001 - 单条规则失败不应中断整个门禁
            findings = [Finding(rule_id, "规则执行异常：%s" % exc, hint="请检查 devflow 版本与仓库结构")]
        for finding in findings:
            finding.severity = finding.severity or severity
            finding.rule = finding.rule or rule_id
            result.findings.append(finding)
    return result


def run_gate(
    root: str, cfg, state: State, phase_id: Optional[str] = None,
    scope: str = "exit", mode: Optional[str] = None,
) -> GateResult:
    phase_id = phase_id or state.current_phase()
    effective_mode = _resolve_mode(cfg, phase_id, mode)
    ctx = Ctx(root, cfg, state, phase_id, scope)
    rule_ids = collect_rules(phase_id, scope, cfg)
    return run_rules(ctx, rule_ids, effective_mode)


def run_all_rules(root: str, cfg, state: State, phase_id: Optional[str] = None,
                  mode: Optional[str] = None) -> GateResult:
    """全量体检：跑一遍契约里出现过的所有规则（用于 `devflow audit`）。"""
    phase_id = phase_id or state.current_phase()
    effective_mode = _resolve_mode(cfg, phase_id, mode)
    ctx = Ctx(root, cfg, state, phase_id, "audit")
    contract = get_active()
    if contract is not None:
        ordered = [rid for rid in contract.all_rule_ids() if _rule_meta(rid) is not None]
        for rid in contract.rules:
            if rid not in ordered and _rule_meta(rid) is not None:
                ordered.append(rid)
    else:
        ordered = []
        for phase in P.enabled_phases(cfg):
            for rid in phase.entry_rules + phase.exit_rules:
                if rid in CHECKS and rid not in ordered:
                    ordered.append(rid)
    return run_rules(ctx, ordered, effective_mode)


def list_rules() -> List[Rule]:
    """内置规则 + 契约里的 DSL 规则。"""
    items: Dict[str, Rule] = dict(RULES)
    contract = get_active()
    if contract is not None:
        for rid, ref in contract.rules.items():
            if ref.is_dsl:
                items[rid] = Rule(id=rid, title=ref.title or rid, category=ref.category,
                                  severity=ref.severity or "warn", source="dsl")
    return sorted(items.values(), key=lambda r: (r.source, r.category, r.id))
