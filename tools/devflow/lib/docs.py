"""文档渲染与解析。

模板解析优先级：
    1) 项目本地覆盖  `{paths.state_dir}/templates/<template>`
    2) Skill 包内置  `<skill>/assets/templates/<template>`
    3) 复制到项目后的 `tools/devflow/templates/<template>`

渲染语法非常克制，只有三类占位符：
    {{KEY}}        直接替换
    {{#if KEY}}...{{/if}}   当 KEY 非空时保留块内内容（块内可嵌占位符）
不引入模板引擎，避免依赖。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import artifacts as A
from . import yamlmini
from .state import now, today

PLACEHOLDER_MARK = "<!-- TODO"

PLACEHOLDER_TOKENS = (
    "TBD", "TODO", "FIXME", "XXX", "<<待补充>>", "<待补充>", "待补充", "???",
)

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.M)


# ---------------------------------------------------------------- 模板目录
def template_dirs(root: str, cfg, skill_root: str) -> List[str]:
    candidates = [
        os.path.join(root, str(cfg.get("paths.state_dir") or ".devflow"), "templates"),
        os.path.join(root, str(cfg.get("paths.tools") or "tools/devflow"), "templates"),
        os.path.join(skill_root, "assets", "templates"),
    ]
    seen: List[str] = []
    for path in candidates:
        real = os.path.abspath(path)
        if real not in seen and os.path.isdir(real):
            seen.append(real)
    return seen


def load_template(cfg, skill_root: str, root: str, name: str) -> str:
    for directory in template_dirs(root, cfg, skill_root):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
    raise FileNotFoundError("找不到模板：%s（搜索目录：%s）" % (name, template_dirs(root, cfg, skill_root)))


def render(template: str, ctx: Dict[str, Any]) -> str:
    text = template
    block = re.compile(r"\{\{#if\s+(\w+)\}\}(.*?)\{\{/if\}\}", re.S)
    def _expand(match: re.Match) -> str:
        if ctx.get(match.group(1)):
            return render(match.group(2), ctx)
        return ""
    for _ in range(3):
        text = block.sub(_expand, text)

    def _value(match: re.Match) -> str:
        key = match.group(1)
        value = ctx.get(key)
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            if not value:
                return "[]"
            return "[" + ", ".join('"%s"' % v for v in value) + "]"
        return str(value)

    return re.sub(r"\{\{(\w+)\}\}", _value, text)


# ---------------------------------------------------------------- 创建
FIELD_DEFAULTS = {
    "id": "{{ID}}",
    "title": "{{TITLE}}",
    "status": "draft",
    "owner": "{{OWNER}}",
    "created": "{{DATE}}",
    "updated": "{{DATE}}",
    "decision_date": "{{DATE}}",
    "retro_date": "{{DATE}}",
    "start_date": "{{DATE}}",
    "reviewers": [],
    "priority": "P1",
    "comments_resolved": False,
    "rollback_ready": False,
    "env_ready": False,
}


def _fmt_field(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    if value is None:
        return '""'
    return str(value)


def generate_template(spec, ctx: Optional[Dict[str, Any]] = None, extra_fields: Optional[List[str]] = None) -> str:
    """按契约自动生成骨架模板。

    自定义产出物类型通常没有现成的 .md 模板文件，此时依据
    `required_fields` 与 `required_sections` 直接生成，保证「声明即可用」。
    """
    ctx = ctx or {}
    fields = list(spec.required_fields or [])
    for field in ("id", "title", "status", "owner"):
        if field not in fields:
            fields.append(field)
    for field in (extra_fields or []):
        if field not in fields:
            fields.append(field)

    lines = ["---"]
    for field in fields:
        lines.append("%s: %s" % (field, _fmt_field(FIELD_DEFAULTS.get(field, '""'))))
    lines += ["phase: %s" % (spec.phase or ""), "---", ""]
    lines += [
        "# {{ID}} {{TITLE}}",
        "",
        "> 类型：%s ｜ 阶段：%s ｜ 负责人：{{OWNER}} ｜ 状态：draft" % (
            spec.label or spec.kind, spec.phase or "-"),
        "> 本模板由 devflow 依据契约自动生成（`<!-- -->` 内是写作提示，写完请删除）。",
        "",
    ]
    sections = spec.required_sections or []
    for index, section in enumerate(sections, 1):
        lines += ["## %d. %s" % (index, section), "", "<!-- TODO: 说明本节要写什么 -->", ""]
    if not sections:
        lines += ["## 内容", "", "<!-- TODO: 说明本节要写什么 -->", ""]
    lines += [
        "---",
        "",
        "> 想让本节被门禁真正校验，请在 `devflow.yaml` 里为该类型补充 required_sections，",
        "> 并在对应阶段的 exit 规则里挂上 `doc.sections` / `doc.frontmatter` 等检查。",
        "",
    ]
    return "\n".join(lines)


def create_document(
    root: str, cfg, skill_root: str, kind: str, title: str,
    owner: str = "", slug: str = "", extra: Optional[Dict[str, Any]] = None,
    seq_id: str = "",
) -> Tuple[str, str, Dict[str, Any]]:
    resolved = A.resolve_kind(kind)
    s = A.spec(resolved)
    title = sanitize_scalar(title)
    art_id = seq_id or A.next_id(root, cfg, resolved)
    file_slug = slug or A.slugify(title, fallback=s.prefix.lower())
    filename = "%s-%s.md" % (art_id, file_slug)
    directory = A.dir_of(root, cfg, resolved)
    rel_dir = os.path.relpath(directory, root).replace("\\", "/")
    rel_path = "%s/%s" % (rel_dir, filename)

    ctx: Dict[str, Any] = {
        "ID": art_id,
        "TITLE": title,
        "OWNER": owner or (cfg.get("project.owner") or ""),
        "DATE": today(),
        "DATETIME": now(),
        "PROJECT": cfg.project_name(),
        "PHASE": s.phase,
        "STATUS": "draft",
        "REVIEWERS": cfg.get("review.min_reviewers") or 1,
    }
    if extra:
        ctx.update(extra)

    content, generated = _render_or_generate(cfg, skill_root, root, s, ctx, extra)
    abs_path = os.path.join(directory, filename)
    os.makedirs(directory, exist_ok=True)
    if os.path.exists(abs_path):
        raise FileExistsError("文档已存在：%s" % rel_path)
    with open(abs_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    front, body = parse_file(abs_path)
    return abs_path, rel_path, {
        "front": front, "body": body, "id": art_id, "kind": resolved,
        "template": "generated" if generated else (s.template or "custom"),
    }


def _render_or_generate(cfg, skill_root: str, root: str, spec, ctx: Dict[str, Any],
                        extra: Optional[Dict[str, Any]]):
    """优先用现成模板；没有模板文件（自定义类型 / skeleton 基线）时按契约生成。"""
    if spec.template:
        try:
            return render(load_template(cfg, skill_root, root, spec.template), ctx), False
        except FileNotFoundError:
            pass
    return render(generate_template(spec, ctx, list((extra or {}).keys())), ctx), True


# ---------------------------------------------------------------- 解析
def parse_text(text: str) -> Tuple[Dict[str, Any], str]:
    front, body = yamlmini.split_front_matter(text)
    return front or {}, body


def parse_file(path: str) -> Tuple[Dict[str, Any], str]:
    with open(path, "r", encoding="utf-8") as fh:
        return parse_text(fh.read())


def headings(body: str) -> List[str]:
    return [m.group(2).strip() for m in _HEADING_RE.finditer(body)]


def strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def section_text(body: str, section: str) -> str:
    """取出某个 `## 小节` 下的正文（不含标题行，遇到同级或更高级标题结束）。

    小节名采用「包含匹配」，允许模板里标题带额外说明文字。
    """
    target = section.strip().lower()
    start_level: Optional[int] = None
    buf: List[str] = []
    collecting = False
    for line in body.split("\n"):
        match = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip().lower()
            if collecting:
                if level <= start_level:
                    break
                buf.append(line)
                continue
            if level == 2 and target in title:
                collecting = True
                start_level = level
            continue
        if collecting:
            buf.append(line)
    return "\n".join(buf).strip()


def missing_sections(body: str, required: List[str]) -> List[str]:
    """小节名采用包含匹配，允许模板里写成 `## 1. 背景与问题`。"""
    present = [h.lower() for h in headings(body)]
    missing = []
    for need in required:
        target = need.lower()
        if not any(target in h for h in present):
            missing.append(need)
    return missing


def find_placeholders(text: str) -> List[Tuple[int, str]]:
    clean = strip_comments(text)
    hits: List[Tuple[int, str]] = []
    seen_tokens = set()
    for lineno, line in enumerate(clean.split("\n"), 1):
        stripped = line.strip()
        if not stripped:
            continue
        for token in PLACEHOLDER_TOKENS:
            if token in line and token not in seen_tokens:
                seen_tokens.add(token)
                hits.append((lineno, token))
    return hits


def empty_fields(front: Dict[str, Any], required: List[str]) -> List[str]:
    missing = []
    for key in required:
        value = front.get(key)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(key)
    return missing


def sanitize_scalar(text: str) -> str:
    """把用户输入压成一行且不会破坏 YAML front-matter 的标量。"""
    cleaned = " ".join(str(text or "").split())
    return cleaned.replace("\\", "/").replace('"', "'")


def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    if value is None:
        return ""
    return str(value)


def set_front_field(path: str, key: str, value: Any) -> bool:
    """就地更新 front-matter 字段，保留其余格式。返回是否被修改。"""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    strict = text.replace("\r\n", "\n").replace("\r", "\n")
    if not strict.startswith("---"):
        return False
    lines = strict.split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return False

    pattern = re.compile(r"^(\s*%s)(\s*:)\s*(.*)$" % re.escape(key))
    rendered = _render_value(value)
    replaced = False
    for i in range(1, end):
        match = pattern.match(lines[i])
        if match:
            lines[i] = "%s: %s" % (match.group(1).rstrip(), rendered)
            replaced = True
            break
    if not replaced:
        lines.insert(end, "%s: %s" % (key, rendered))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return True


def sync_reviewer(path: str, name: str) -> bool:
    """把评审人追加到文档头部的 reviewers 字段（字段不存在时不新增）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            front, _ = split_front_matter_by_line(fh.read())
    except OSError:
        return False
    if not front or "reviewers" not in front:
        return False
    current = front.get("reviewers") or []
    if isinstance(current, str):
        current = [v.strip() for v in current.split(",") if v.strip()]
    current = list(current)
    if name in current:
        return True
    current.append(name)
    return set_front_field(path, "reviewers", current)


def split_front_matter_by_line(text: str) -> tuple:
    """返回 (front dict, body)；供需要精确控制写回位置的场景使用。"""
    return parse_text(text)


def checklist_stats(body: str) -> Dict[str, int]:
    checked = len(re.findall(r"^\s*[-*]\s+\[[xX]\]", body, re.M))
    unchecked = len(re.findall(r"^\s*[-*]\s+\[\s\]", body, re.M))
    return {"checked": checked, "unchecked": unchecked, "total": checked + unchecked}


INDEX_START = "<!-- devflow:index:start -->"
INDEX_END = "<!-- devflow:index:end -->"


def refresh_index(root: str, cfg, state, targets: Optional[List[str]] = None) -> Optional[str]:
    """把已登记的交付物写回索引文档中 `devflow:index` 标记之间的区域。

    targets 为空时在 docs 根目录与 README.md 中查找第一个带标记的索引文件。
    """
    docs_root = str(cfg.get("paths.docs") or "docs")
    candidates = [
        "%s/README.md" % docs_root, "%s/INDEX.md" % docs_root,
        "%s/index.md" % docs_root, "README.md",
    ]
    if targets:
        candidates = list(targets) + candidates
    for cand in candidates:
        path = os.path.join(root, cand)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if INDEX_START not in text or INDEX_END not in text:
            continue
        rows = []
        for item in state.artifacts():
            rows.append("| %s | %s | %s | [%s](%s) |" % (
                item.get("id", "-"), item.get("kind", "-"),
                str(item.get("title") or "-").replace("|", "\\|"),
                item.get("path", "-"), "../" + item.get("path", "") if cand.startswith(docs_root + "/") else item.get("path", ""),
            ))
        if not rows:
            rows = ["| - | - | 暂无 | - |"]
        body = "\n".join([
            INDEX_START,
            "<!-- 本段由 devflow 自动生成，修改请提交流程命令 -->",
            "",
            "| 编号 | 类型 | 标题 | 路径 |",
            "| --- | --- | --- | --- |",
            *rows,
            "",
            INDEX_END,
        ])
        pattern = re.compile(re.escape(INDEX_START) + r".*?" + re.escape(INDEX_END), re.S)
        new_text = pattern.sub(lambda _: body, text, count=1)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_text)
        return cand
    return None


def ensure_dirs(root: str, cfg) -> List[str]:
    created = []
    for kind in A.all_kinds():
        directory = A.dir_of(root, cfg, kind)
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
            created.append(os.path.relpath(directory, root).replace("\\", "/"))
    docs = os.path.join(root, str(cfg.get("paths.docs") or "docs"))
    if not os.path.isdir(docs):
        os.makedirs(docs, exist_ok=True)
        created.append(cfg.get("paths.docs") or "docs")
    return created
