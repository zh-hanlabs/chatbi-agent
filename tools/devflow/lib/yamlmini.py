"""yamlmini —— 零依赖的极简 YAML 子集解析器。

devflow 用它解析项目配置 `devflow.yaml` 与 Markdown 文档的 YAML front-matter，
避免引入 PyYAML，从而保证在任何 CI 环境中开箱即用。

支持的子集：
  * 注释：整行注释与行尾注释（`#` 出现在引号外才生效）
  * `key: value`，标量自动推断为 null / bool / int / float / str
  * 嵌套映射：由缩进决定层级（同缩进 `- ` 开头的序列也算）
  * 序列：`- item`、`- key: value` 及其任意嵌套
  * 行内结构：`[a, b, c]`、`{a: 1, b: two}`
  * 块标量：`|`、`>` 及其 `-` / `+` chomping 形式

不支持：锚点与别名（`&a` / `*a`）、多文档、复杂键、`?` 显式键、tag（`!!str`）。
块标量内部的空行会被折叠为单行前的换行（够用但不追求完全兼容）。

若配置确实需要上述能力，请改用 `devflow.json`（devflow 会自动识别 JSON 配置）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

__all__ = ["loads", "load", "split_front_matter", "YamlMiniError"]


class YamlMiniError(ValueError):
    """YAML 文本超出支持子集或格式非法。"""


_INT_RE = r"^[+-]?\d+$"
_FLOAT_RE = r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$"

_TRUE = ("true", "True", "TRUE")
_FALSE = ("false", "False", "FALSE")
_NULL = ("", "~", "null", "Null", "NULL")


class _Line:
    __slots__ = ("indent", "content", "lineno")

    def __init__(self, indent: int, content: str, lineno: int):
        self.indent = indent
        self.content = content
        self.lineno = lineno

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return "<Line %d indent=%d %r>" % (self.lineno, self.indent, self.content)


def _strip_comment(line: str) -> str:
    """去掉引号之外的注释。"""
    out: List[str] = []
    quote: Optional[str] = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _read_lines(text: str) -> List[_Line]:
    lines: List[_Line] = []
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    pending: Optional[Tuple[int, List[str], int]] = None   # (indent, 已累积片段, 起始行号)

    for lineno, original in enumerate(raw, 1):
        content = _strip_comment(original)
        stripped = content.strip()
        if not stripped:
            continue
        if stripped in ("---", "..."):
            continue
        content = content.rstrip()
        if content[:1] == "\t":
            raise YamlMiniError("第 %d 行使用了 Tab 缩进，请改用空格缩进" % lineno)
        lead = len(content) - len(content.lstrip(" "))
        body = content.lstrip(" ")

        if pending is not None:
            indent, parts, start = pending
            parts.append(body)
            joined = " ".join(p.strip() for p in parts)
            if _flow_unterminated(joined):
                pending = (indent, parts, start)
            else:
                lines.append(_Line(indent, joined, start))
                pending = None
            continue

        if _flow_unterminated(body):
            pending = (lead, [body], lineno)
            continue
        lines.append(_Line(lead, body, lineno))

    if pending is not None:      # 文件结束时仍未闭合：按已收集内容尽力解析
        indent, parts, start = pending
        lines.append(_Line(indent, " ".join(p.strip() for p in parts), start))
    return lines


def _flow_unterminated(content: str) -> bool:
    """行内集合是否未闭合（支持 `key: [a, b,` 换行续写）。"""
    depth = 0
    quote: Optional[str] = None
    i = 0
    n = len(content)
    while i < n:
        ch = content[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        i += 1
    return depth > 0


def _split_key(content: str) -> Optional[Tuple[str, str]]:
    """把 `key: value` 切成 (key, rest)。非键值对返回 None。"""
    quote: Optional[str] = None
    i = 0
    n = len(content)
    while i < n:
        ch = content[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == ":" and (i + 1 == n or content[i + 1] in " \t"):
            return content[:i].strip(), content[i + 1:].strip()
        i += 1
    return None


def _looks_like_pair(content: str) -> bool:
    kv = _split_key(content)
    return kv is not None


def _is_flow(value: str) -> bool:
    return (value.startswith("[") and value.endswith("]")) or (
        value.startswith("{") and value.endswith("}")
    )


def _split_flow(body: str) -> List[str]:
    """按顶层逗号切分行内集合。"""
    parts: List[str] = []
    depth = 0
    quote: Optional[str] = None
    buf: List[str] = []
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                buf.append(body[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _unescape_double(text: str) -> str:
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}
            out.append(mapping.get(nxt, "\\" + nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _scalar(token: str) -> Any:
    value = token.strip()
    if value in _NULL:
        return None
    if len(value) >= 2:
        if value[0] == '"' and value[-1] == '"':
            return _unescape_double(value[1:-1])
        if value[0] == "'" and value[-1] == "'":
            return value[1:-1].replace("''", "'")
    if _is_flow(value):
        if value.startswith("["):
            body = value[1:-1].strip()
            if not body:
                return []
            return [_scalar(p) for p in _split_flow(body)]
        body = value[1:-1].strip()
        if not body:
            return {}
        flow: Dict[str, Any] = {}
        for part in _split_flow(body):
            kv = _split_key(part)
            if kv is None:
                raise YamlMiniError("行内映射项无法解析：%r" % part)
            k, v = kv
            flow[str(_scalar(k))] = _scalar(v)
        return flow
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    import re

    if re.match(_INT_RE, value):
        try:
            return int(value)
        except ValueError:  # pragma: no cover
            return value
    if re.match(_FLOAT_RE, value):
        try:
            return float(value)
        except ValueError:  # pragma: no cover
            return value
    return value


def _parse_block_scalar(
    lines: List[_Line], idx: int, indent: int, indicator: str
) -> Tuple[str, int]:
    style = indicator[0]
    chomp = indicator[1:] if len(indicator) > 1 else ""
    buf: List[str] = []
    base: Optional[int] = None
    n = len(lines)
    while idx < n and lines[idx].indent > indent:
        line = lines[idx]
        if base is None:
            base = line.indent
        if line.indent < base:
            break
        buf.append(" " * (line.indent - base) + line.content)
        idx += 1
    text = " ".join(s.strip() for s in buf) if style == ">" else "\n".join(buf)
    if chomp == "-":
        text = text.rstrip("\n")
    elif chomp == "":
        text = text.rstrip("\n") + "\n" if buf else ""
    return text, idx


def _parse_seq(lines: List[_Line], idx: int, indent: int) -> Tuple[List[Any], int]:
    result: List[Any] = []
    n = len(lines)
    while idx < n and lines[idx].indent == indent and (
        lines[idx].content == "-" or lines[idx].content.startswith("- ")
    ):
        lineno = lines[idx].lineno
        rest = lines[idx].content[1:].strip()
        idx += 1
        if not rest:
            if idx < n and lines[idx].indent > indent:
                value, idx = _parse_block(lines, idx, lines[idx].indent)
            else:
                value = None
            result.append(value)
            continue
        following: List[_Line] = []
        while idx < n and lines[idx].indent > indent:
            following.append(lines[idx])
            idx += 1
        if not rest.startswith(("{", "[")) and _looks_like_pair(rest):
            virtual = following[0].indent if following else indent + 2
            sub = [_Line(virtual, rest, lineno)] + following
            value, _ = _parse_block(sub, 0, sub[0].indent)
            result.append(value)
        else:
            result.append(_scalar(rest))
    return result, idx


def _parse_map(lines: List[_Line], idx: int, indent: int) -> Tuple[Dict[str, Any], int]:
    result: Dict[str, Any] = {}
    n = len(lines)
    while idx < n and lines[idx].indent == indent:
        content = lines[idx].content
        if content == "-" or content.startswith("- "):
            break
        kv = _split_key(content)
        if kv is None:
            raise YamlMiniError("第 %d 行无法解析为 `键: 值`：%r" % (lines[idx].lineno, content))
        key, rest = kv
        lineno = lines[idx].lineno
        idx += 1
        if rest:
            if rest in ("|", "|-", "|+", ">", ">-", ">+"):
                value, idx = _parse_block_scalar(lines, idx, indent, rest)
            else:
                value = _scalar(rest)
            name = str(_scalar(key))
            if name in result:
                raise YamlMiniError("第 %d 行出现重复的键 `%s`（后者会静默覆盖前者）" % (lineno, name))
            result[name] = value
            continue
        if idx < n and (
            lines[idx].indent > indent
            or (lines[idx].indent == indent and lines[idx].content.startswith("- "))
        ):
            value, idx = _parse_block(lines, idx, lines[idx].indent)
        else:
            value = None
        name = str(_scalar(key))
        if name in result:
            raise YamlMiniError("第 %d 行出现重复的键 `%s`（后者会静默覆盖前者）" % (lineno, name))
        result[name] = value
    return result, idx


def _parse_block(lines: List[_Line], idx: int, indent: int) -> Tuple[Any, int]:
    content = lines[idx].content
    if content == "-" or content.startswith("- "):
        return _parse_seq(lines, idx, indent)
    return _parse_map(lines, idx, indent)


def loads(text: str) -> Any:
    """解析 YAML 文本，返回 dict / list / None。"""
    lines = _read_lines(text)
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, lines[0].indent)
    return value


def load(path: str) -> Any:
    """读取文件或 stdin 标记 `-`。自动识别 JSON 与 YAML。"""
    if path == "-":
        text = __import__("sys").stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    stripped = text.lstrip()
    if stripped[:1] in "{[":
        import json

        return json.loads(text)
    return loads(text)


def split_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    """拆分 Markdown front-matter，返回 (front, body)。

    没有 front-matter 时返回 ({}, 原文)。
    """
    strict = text.replace("\r\n", "\n").replace("\r", "\n")
    if not strict.startswith("---"):
        return {}, text
    lines = strict.split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return {}, text
    front = loads("\n".join(lines[1:end]))
    if not isinstance(front, dict):
        raise YamlMiniError("front-matter 必须是键值映射")
    return front, "\n".join(lines[end + 1:])
