"""检查原语（DSL 的执行单元）。

契约里的一条自定义规则由若干 check 组成，每个 check 指定一个原语：

```yaml
rules:
  - id: custom.no-system-out
    title: 禁止提交 System.out.println
    severity: error
    checks:
      - type: file_not_contains
        glob: "src/**/*.java"
        pattern: "System\\.out\\.println"
        message: "发现调试输出"
```

原语只回答「有没有问题」，严重级别由所属规则决定，因此同一原语既能当
error 也能当 warn，复用成本极低。

`devflow contract primitives` 可查看全部原语及其参数。
"""

from __future__ import annotations

import glob as globmod
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional

from . import docs as D
from .model import Finding

PRIMITIVES: Dict[str, Callable[[Any, Dict[str, Any], str], List[Finding]]] = {}
HELP: Dict[str, str] = {}


def primitive(name: str, params: str):
    def decorator(fn: Callable) -> Callable:
        PRIMITIVES[name] = fn
        HELP[name] = params
        return fn
    return decorator


# ------------------------------------------------------------------ 小工具
def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _msg(check: Dict[str, Any], default: str) -> str:
    return str(check.get("message") or default)


def _hint(check: Dict[str, Any]) -> str:
    return str(check.get("hint") or "")


def _loc(check: Dict[str, Any], default: str = "") -> str:
    return str(check.get("location") or default)


def _make(ctx, check: Dict[str, Any], rule_id: str, message: str, location: str = "") -> Finding:
    return Finding(rule=rule_id, message=_msg(check, message),
                   location=_loc(check, location), hint=_hint(check))


def _target_paths(ctx, check: Dict[str, Any]) -> List[str]:
    """解析原语的作用目标：显式 paths、glob 或 kinds（产出物类型）。"""
    paths = [str(p) for p in _as_list(check.get("paths"))]
    if not paths and check.get("path"):
        paths = [str(check["path"])]
    if not paths and check.get("glob"):
        paths = ctx.glob(str(check["glob"]))
    return paths


def _target_docs(ctx, check: Dict[str, Any]) -> List[Dict[str, Any]]:
    kinds = [str(k) for k in _as_list(check.get("kinds"))]
    if kinds:
        return ctx.docs(kinds)
    paths = _target_paths(ctx, check)
    result = []
    for rel in paths:
        info = ctx.doc(rel)
        if info is not None:
            result.append(dict({"kind": "", "path": rel, "record": None}, **info))
    return result


def _compile(pattern: str, flags: str = "") -> re.Pattern:
    value = 0
    flags = (flags or "").lower()
    if "i" in flags:
        value |= re.I
    if "m" in flags:
        value |= re.M
    if "s" in flags:
        value |= re.S
    return re.compile(pattern, value)


# ------------------------------------------------------------------ 文件类
@primitive("file_exists", "paths[] | path：必需存在的文件/目录")
def _p_file_exists(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    findings = []
    for rel in _target_paths(ctx, check):
        if not os.path.exists(ctx.abs(rel)):
            findings.append(_make(ctx, check, rid, "缺少必需文件：%s" % rel, rel))
    return findings


@primitive("file_absent", "paths[] | path：禁止出现的文件")
def _p_file_absent(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    findings = []
    for rel in _target_paths(ctx, check):
        if os.path.exists(ctx.abs(rel)):
            findings.append(_make(ctx, check, rid, "不应存在的文件：%s" % rel, rel))
    return findings


@primitive("glob_exists", "glob + min(默认1)：匹配数量下限")
def _p_glob_exists(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    matched = ctx.glob(str(check.get("glob") or ""))
    minimum = int(check.get("min", 1) or 1)
    if len(matched) < minimum:
        return [_make(ctx, check, rid, "匹配 %s 的文件只有 %d 个（要求 ≥%d）" % (
            check.get("glob"), len(matched), minimum))]
    return []


@primitive("glob_forbidden", "glob：禁止出现匹配该模式的文件")
def _p_glob_forbidden(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    matched = ctx.glob(str(check.get("glob") or ""))
    if not matched:
        return []
    sample = "、".join(matched[:5])
    return [_make(ctx, check, rid, "存在 %d 个被禁止的文件，例如：%s" % (len(matched), sample),
                  matched[0])]


@primitive("file_contains", "paths[]|glob + pattern + min_matches(默认1)：必须命中")
def _p_file_contains(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    pattern = _compile(str(check.get("pattern") or ""), str(check.get("flags") or ""))
    minimum = int(check.get("min_matches", 1) or 1)
    hits = 0
    scanned: List[str] = []
    for rel in _target_paths(ctx, check):
        if not os.path.isfile(ctx.abs(rel)):
            continue
        scanned.append(rel)
        try:
            with open(ctx.abs(rel), "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        if pattern.search(text):
            hits += 1
    if hits >= minimum:
        return []
    return [_make(ctx, check, rid,
                  "扫描 %d 个文件，只有 %d 个命中 %s（要求 ≥%d）" % (
                      len(scanned), hits, check.get("pattern"), minimum))]


@primitive("file_not_contains", "paths[]|glob + pattern：不得命中（逐行定位）")
def _p_file_not_contains(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    pattern = _compile(str(check.get("pattern") or ""), str(check.get("flags") or ""))
    findings = []
    limit = int(check.get("max_hits", 5) or 5)
    for rel in _target_paths(ctx, check):
        path = ctx.abs(rel)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().split("\n")
        except OSError:
            continue
        for index, line in enumerate(lines, 1):
            if pattern.search(line):
                findings.append(_make(
                    ctx, check, rid, "命中禁用模式 %s：%s" % (check.get("pattern"), line.strip()[:60]),
                    "%s:%d" % (rel, index)))
                if len(findings) >= limit:
                    return findings
    return findings


# ------------------------------------------------------------------ 产出物类
@primitive("artifact_fields", "kinds[] + fields[]：front-matter 必填字段")
def _p_artifact_fields(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    fields = [str(f) for f in _as_list(check.get("fields"))]
    findings = []
    for item in _target_docs(ctx, check):
        missing = D.empty_fields(item["front"], fields)
        if missing:
            findings.append(_make(ctx, check, rid,
                                  "%s 缺少字段：%s" % (item["path"], "、".join(missing)), item["path"]))
    return findings


@primitive("artifact_sections", "kinds[] + sections[]：正文必填小节")
def _p_artifact_sections(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    sections = [str(s) for s in _as_list(check.get("sections"))]
    findings = []
    for item in _target_docs(ctx, check):
        missing = D.missing_sections(item["body"], sections)
        if missing:
            findings.append(_make(ctx, check, rid,
                                  "%s 缺少小节：%s" % (item["path"], "、".join(missing)), item["path"]))
    return findings


@primitive("artifact_placeholder", "kinds[]：不得残留 TODO/TBD 等占位符")
def _p_artifact_placeholder(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    findings = []
    for item in _target_docs(ctx, check):
        hits = D.find_placeholders(item["text"])
        if hits:
            detail = "、".join("第 %d 行 %s" % (lineno, token) for lineno, token in hits[:3])
            findings.append(_make(ctx, check, rid, "%s 仍有占位符：%s" % (item["path"], detail),
                                  item["path"]))
    return findings


@primitive("artifact_status", "kinds[] + equals：front-matter status 必须等于指定值")
def _p_artifact_status(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    expected = str(check.get("equals") or "approved").lower()
    findings = []
    for item in _target_docs(ctx, check):
        actual = str(item["front"].get("status") or "").lower()
        if actual != expected:
            findings.append(_make(ctx, check, rid, "%s 的 status=%s（要求 %s）" % (
                item["path"], actual or "空", expected), item["path"]))
    return findings


@primitive("artifact_approved_by", "kinds[] + min：不同评审人数量下限")
def _p_artifact_approved_by(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    minimum = int(check.get("min", 1) or 1)
    findings = []
    for item in _target_docs(ctx, check):
        art_id = str(item["front"].get("id") or "")
        names = {a.get("by") for a in ctx.state.approvals_for(art_id)
                 if a.get("by") and a.get("decision") != "request_changes"}
        reviewers = item["front"].get("reviewers") or []
        if isinstance(reviewers, str):
            reviewers = [r.strip() for r in reviewers.split(",") if r.strip()]
        names |= set(reviewers)
        if len(names) < minimum:
            findings.append(_make(ctx, check, rid, "%s 评审人数 %d/%d" % (
                item["path"], len(names), minimum), item["path"]))
    return findings


@primitive("artifact_exists", "kinds[]：该类型至少存在一份文档")
def _p_artifact_exists(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    from . import artifacts as A
    findings = []
    for kind in [str(k) for k in _as_list(check.get("kinds"))]:
        try:
            resolved = A.resolve_kind(kind)
        except KeyError:
            findings.append(_make(ctx, check, rid, "契约未定义产出物类型：%s" % kind))
            continue
        if not A.list_files(ctx.root, ctx.cfg, resolved):
            s = A.spec(resolved)
            findings.append(_make(ctx, check, rid, "缺少产出物：%s" % (s.label or resolved)))
    return findings


@primitive("artifact_section_min", "kinds[] + section + min_chars：小节内容长度下限")
def _p_artifact_section_min(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    section = str(check.get("section") or "")
    minimum = int(check.get("min_chars", 40) or 40)
    findings = []
    for item in _target_docs(ctx, check):
        content = D.strip_comments(D.section_text(item["body"], section))
        content = re.sub(r"^>\s?.*$", "", content, flags=re.M).strip()
        if len(content) < minimum:
            findings.append(_make(ctx, check, rid, "%s 的『%s』仅 %d 字（要求 ≥%d）" % (
                item["path"], section, len(content), minimum), item["path"]))
    return findings


@primitive("artifact_checklist", "kinds[]：checklist 必须全部勾选")
def _p_artifact_checklist(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    findings = []
    for item in _target_docs(ctx, check):
        stats = D.checklist_stats(item["body"])
        if stats["total"] == 0:
            findings.append(_make(ctx, check, rid, "%s 没有 checklist" % item["path"], item["path"]))
        elif stats["unchecked"]:
            findings.append(_make(ctx, check, rid, "%s 有 %d 项未勾选" % (
                item["path"], stats["unchecked"]), item["path"]))
    return findings


# ------------------------------------------------------------------ 表格类
@primitive("table_column", "kinds[]|paths[] + sections[] + column + allow[]|deny[] + where_*")
def _p_table_column(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    from .gates import _tables, _col_index, _cell
    column = str(check.get("column") or "")
    allow = [str(v).lower() for v in _as_list(check.get("allow"))]
    deny = [str(v).lower() for v in _as_list(check.get("deny"))]
    sections = [str(s) for s in _as_list(check.get("sections"))]
    where_column = str(check.get("where_column") or "")
    where_in = [str(v).lower() for v in _as_list(check.get("where_in"))]
    findings = []
    for item in _target_docs(ctx, check):
        body = "\n".join(D.section_text(item["body"], s) for s in sections) if sections else item["body"]
        for table in _tables(body):
            idx = _col_index(table["headers"], column)
            if idx is None:
                continue
            where_idx = _col_index(table["headers"], where_column) if where_column else None
            id_idx = _col_index(table["headers"], "编号", "ID", "id", "用例", "缺陷")
            for lineno, row in table["rows"]:
                if len(row) < 2:
                    continue
                if where_idx is not None and where_in:
                    if str(_cell(row, where_idx)).strip().lower() not in where_in:
                        continue
                value = str(_cell(row, idx)).strip()
                label = str(_cell(row, id_idx) or "").strip()
                location = "%s:%d" % (item["path"], lineno)
                if allow and value.lower() not in allow:
                    findings.append(_make(ctx, check, rid, "%s 的『%s』为 %r（允许：%s）" % (
                        label or item["path"], column, value or "空", "/".join(allow)), location))
                elif deny and value.lower() in deny:
                    findings.append(_make(ctx, check, rid, "%s 的『%s』为 %r（不允许）" % (
                        label or item["path"], column, value), location))
    return findings


@primitive("table_min_rows", "kinds[]|paths[] + sections[] + min：表格行数下限")
def _p_table_min_rows(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    from .gates import _tables
    minimum = int(check.get("min", 1) or 1)
    sections = [str(s) for s in _as_list(check.get("sections"))]
    findings = []
    for item in _target_docs(ctx, check):
        body = "\n".join(D.section_text(item["body"], s) for s in sections) if sections else item["body"]
        rows = sum(len(t["rows"]) for t in _tables(body))
        if rows < minimum:
            findings.append(_make(ctx, check, rid, "%s 的记录只有 %d 行（要求 ≥%d）" % (
                item["path"], rows, minimum), item["path"]))
    return findings


# ------------------------------------------------------------------ 仓库 / git
@primitive("git_branch", "pattern | patterns{}：分支名必须匹配")
def _p_git_branch(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    if not ctx.is_repo():
        return [Finding(rule=rid, message="非 git 仓库，跳过分支检查",
                        severity="info", hint=_hint(check))]
    branch = ctx.branch()
    patterns = check.get("patterns")
    candidates: List[str] = []
    if isinstance(patterns, dict):
        candidates = [str(v) for v in patterns.values() if v]
    elif check.get("pattern"):
        candidates = [str(check["pattern"])]
    if not candidates:
        return []
    for pattern in candidates:
        if re.match(pattern, branch or ""):
            return []
    return [_make(ctx, check, rid, "分支 `%s` 不匹配规范：%s" % (branch, " 或 ".join(candidates)))]


@primitive("git_log", "pattern + limit(默认20)：提交信息必须匹配（跳过 Merge 提交）")
def _p_git_log(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    if not ctx.is_repo():
        return [Finding(rule=rid, message="非 git 仓库，跳过提交检查",
                        severity="info", hint=_hint(check))]
    limit = int(check.get("limit", 20) or 20)
    ok, out = ctx.git("log", "-%d" % limit, "--format=%s")
    subjects = [line.strip() for line in (out or "").split("\n") if line.strip()]
    if not subjects:
        return []
    pattern = _compile(str(check.get("pattern") or ""), str(check.get("flags") or ""))
    bad = [s for s in subjects if not s.startswith("Merge ") and not pattern.match(s)]
    if not bad:
        return []
    return [_make(ctx, check, rid, "最近 %d 条提交中 %d 条不符合规范，例如：%s" % (
        len(subjects), len(bad), bad[0][:60]))]


@primitive("git_clean", "ignore[]：工作区不得有未提交改动")
def _p_git_clean(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    if not ctx.is_repo():
        return [Finding(rule=rid, message="非 git 仓库，跳过", severity="info")]
    ok, out = ctx.git("status", "--porcelain")
    if not ok:
        return []
    ignore = set(str(p) for p in _as_list(check.get("ignore")))
    changes = []
    for line in (out or "").split("\n"):
        if not line.strip():
            continue
        path = line[2:].lstrip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path.strip().strip('"') in ignore:
            continue
        changes.append(line.strip())
    if not changes:
        return []
    return [_make(ctx, check, rid, "有 %d 处未提交改动，例如：%s" % (len(changes), changes[0][:60]))]


@primitive("git_tag", "equals | pattern：tag 必须存在")
def _p_git_tag(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    if not ctx.is_repo():
        return []
    ok, out = ctx.git("tag", "--list")
    tags = [t.strip() for t in (out or "").split("\n") if t.strip()]
    wanted = check.get("equals")
    if wanted:
        wanted = str(wanted)
        return [] if wanted in tags else [_make(ctx, check, rid, "git tag %s 不存在" % wanted)]
    pattern = check.get("pattern")
    if pattern:
        cregex = _compile(str(pattern))
        return [] if any(cregex.match(t) for t in tags) else [
            _make(ctx, check, rid, "没有匹配 %s 的 tag" % pattern)]
    return []


# ------------------------------------------------------------------ 任务 / 指标 / 命令
@primitive("task_field", "fields[]：任务不得缺少这些字段（默认跳过 done/cancelled）")
def _p_task_field(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    fields = [str(f) for f in _as_list(check.get("fields"))]
    issues = []
    for task in ctx.state.tasks():
        if task.get("status") in ("done", "cancelled"):
            continue
        missing = [f for f in fields if not task.get(f)]
        if missing:
            issues.append("%s(%s) 缺 %s" % (task.get("id"), task.get("title"), "/".join(missing)))
    if not issues:
        return []
    return [_make(ctx, check, rid, "%d 个任务字段不全：%s" % (len(issues), "；".join(issues[:5])))]


@primitive("task_blocking_done", "：--blocking 标记的任务必须完成")
def _p_task_blocking_done(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    from . import tasks as T
    pending = T.blocking_open(ctx.state.tasks())
    if not pending:
        return []
    return [_make(ctx, check, rid, "阻塞任务未完成：%s" % "、".join(
        "%s(%s)" % (t["id"], t.get("title")) for t in pending))]


def _read_number(path: str, key: str) -> Optional[float]:
    try:
        if path.endswith(".xml"):
            root = ET.parse(path).getroot()
            for attr in ("line-rate", "lines-covered-rate", key):
                if attr in root.attrib:
                    value = float(root.attrib[attr])
                    return value * 100 if value <= 1 else value
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001 - 指标文件缺失或格式异常由调用方提示
        return None
    node: Any = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    if isinstance(node, (int, float)):
        return float(node)
    return None


@primitive("metric", "file + key + min|max：数值指标越界")
def _p_metric(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    rel = str(check.get("file") or "")
    key = str(check.get("key") or "")
    path = ctx.abs(rel) if rel else None
    value: Optional[float] = None
    if path and os.path.isfile(path):
        value = _read_number(path, key)
    if value is None:
        return [_make(ctx, check, rid, "未读取到指标 %s（文件：%s）" % (key, rel or "未指定"), rel)]
    minimum = check.get("min")
    maximum = check.get("max")
    if minimum is not None and value < float(minimum):
        return [_make(ctx, check, rid, "%s = %s，低于下限 %s" % (key, value, minimum), rel)]
    if maximum is not None and value > float(maximum):
        return [_make(ctx, check, rid, "%s = %s，高于上限 %s" % (key, value, maximum), rel)]
    return []


@primitive("command", "cmd + expect_exit(默认0) + timeout(默认120)：命令退出码")
def _p_command(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    cmd = str(check.get("cmd") or "").strip()
    if not cmd:
        return [_make(ctx, check, rid, "原语 command 缺少 cmd")]
    expected = int(check.get("expect_exit", 0) or 0)
    timeout = int(check.get("timeout", 120) or 120)
    try:
        proc = subprocess.run(cmd, cwd=ctx.root, shell=True, timeout=timeout,
                              capture_output=True, text=True, errors="replace")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        return [_make(ctx, check, rid, "命令超时（%ds）：%s" % (timeout, cmd))]
    except OSError as exc:
        return [_make(ctx, check, rid, "命令无法执行：%s（%s）" % (cmd, exc))]
    if code != expected:
        return [_make(ctx, check, rid, "命令退出码 %d（期望 %d）：%s" % (code, expected, cmd))]
    return []


@primitive("doc_index", "paths[]：文档索引必须收录全部产出物")
def _p_doc_index(ctx, check: Dict[str, Any], rid: str) -> List[Finding]:
    candidates = [str(p) for p in _as_list(check.get("paths"))]
    content = ""
    chosen = ""
    for rel in candidates:
        if os.path.isfile(ctx.abs(rel)):
            chosen = rel
            with open(ctx.abs(rel), "r", encoding="utf-8") as fh:
                content = fh.read()
            break
    if not chosen:
        return [_make(ctx, check, rid, "未找到文档索引（%s）" % (candidates[0] if candidates else "?"))]
    missing = [item["path"] for item in ctx.all_docs() if item["path"] not in content]
    if not missing:
        return []
    return [_make(ctx, check, rid, "%s 未收录：%s" % (chosen, "、".join(missing[:8])), chosen)]


def run_check(ctx, check: Dict[str, Any], rule_id: str) -> List[Finding]:
    """执行单个原语检查；未知类型返回一条 warn 级提示而不是崩溃。"""
    ptype = str(check.get("type") or "")
    fn = PRIMITIVES.get(ptype)
    if fn is None:
        return [Finding(rule=rule_id,
                        message="未知检查原语：%s（可用：%s）" % (ptype, "、".join(sorted(PRIMITIVES))),
                        severity="warn")]
    try:
        return fn(ctx, check, rule_id) or []
    except Exception as exc:  # noqa: BLE001 - 单条检查失败不应中断门禁
        return [Finding(rule=rule_id, message="检查 %s 执行异常：%s" % (ptype, exc), severity="warn")]


def run_all(ctx, checks: List[Dict[str, Any]], rule_id: str) -> List[Finding]:
    findings: List[Finding] = []
    for check in checks:
        findings.extend(run_check(ctx, check, rule_id))
    return findings


def describe() -> List[Dict[str, str]]:
    return [{"type": name, "params": params} for name, params in sorted(HELP.items())]
