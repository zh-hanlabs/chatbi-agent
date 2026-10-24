"""配置加载：默认配置 + 项目配置深合并。

配置文件优先级（在仓库根目录查找，命中第一个）：
    devflow.yaml  >  devflow.yml  >  devflow.json  >  内置默认
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

from . import yamlmini

__all__ = ["Config", "DEFAULT_CONFIG", "load_config", "write_config", "dump_yaml"]

CONFIG_FILENAMES = ("devflow.yaml", "devflow.yml", "devflow.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "project": {
        "name": "",
        "slug": "",
        "owner": "",
        "team": "",
        "repo": "",
    },
    "platform": {
        "ci": "github",          # github | gitlab | jenkins | cnb | none
        "hosting": "github",     # github | gitlab | jenkins | cnb | other
    },
    "paths": {
        "docs": "docs",
        "requirements": "docs/requirements",
        "design": "docs/design",
        "adr": "docs/adr",
        "plan": "docs/plan",
        "review": "docs/review",
        "test": "docs/test",
        "release": "docs/release",
        "retro": "docs/retro",
        "tools": "tools/devflow",
        "state_dir": ".devflow",
        "changelog": "CHANGELOG.md",
    },
    "phases": {
        "enabled": [
            "intake", "design", "plan", "develop", "review", "test", "release", "retro",
        ],
    },
    "artifacts": {
        "optional": ["adr"],
    },
    "gates": {
        "mode": "graded",        # strict（全部升为 error） | graded（按规则自身级别）| warn（全部降级）| off
        "phase_modes": {         # 阶段级覆盖；未列出的阶段沿用 gates.mode
            "release": "strict",
            "review": "graded",
        },
    },
    "rules": {
        "severity": {},          # 规则级覆盖：{"repo.commit": "error"}
        "disabled": [],          # 停用的规则 id
    },
    "review": {
        "min_reviewers": 1,
        "required_roles": ["reviewer"],
        "max_open_comment_days": 3,
    },
    "test": {
        "min_coverage": 70.0,
        "min_cases": 3,
        "coverage_report": "",   # 留空则自动探测 coverage.json / coverage.xml
        "require_smoke": True,
    },
    "repo": {
        "hosting_branch": "main",
        "develop_branch": "develop",
        "branch_patterns": {
            "feature": "^feature/[A-Za-z0-9._-]+-[A-Za-z0-9._-]+$",
            "fix": "^(fix|hotfix)/[A-Za-z0-9._-]+-[A-Za-z0-9._-]+$",
            "release": "^release/v[0-9]+\\.[0-9]+\\.[0-9]+$",
        },
        "commit_types": [
            "feat", "fix", "docs", "style", "refactor", "perf", "test",
            "build", "ci", "chore", "revert",
        ],
        "commit_scope_required": False,
        "max_file_mb": 5,
        "max_line_length": 0,        # 0 表示不检查
        "ignore_paths": [
            ".git/", "node_modules/", "target/", "build/", "dist/",
            "venv/", ".venv/", "__pycache__/", ".devflow/",
        ],
        "secret_patterns": [
            "-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----",
            "AKIA[0-9A-Z]{16}",
            "ghp_[A-Za-z0-9]{36,}",
            "gho_[A-Za-z0-9]{36,}",
            "sk-[A-Za-z0-9]{32,}",
            "xox[baprs]-[A-Za-z0-9-]{10,}",
            "(?:access[_-]?key|secret[_-]?key|client[_-]?secret)[\\s]*[=:][\\s]*['\"][^'\"\\s]{8,}['\"]",
            "(?:password|passwd|pwd)[\\s]*[=:][\\s]*['\"][^'\"\\s]{8,}['\"]",
        ],
    },
    "ci": {
        "status_file": ".devflow/ci-status.json",
        "python": "python3",
        "required_jobs": ["gate"],
    },
    "release": {
        "require_tag": True,
        "require_changelog": True,
        "tag_prefix": "v",
        "freeze_window_hours": 0,
    },
    "report": {
        "status_file": ".devflow/STATUS.md",
        "publish_to": "docs/STATUS.md",
        "recent_events": 10,
    },
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """把 override 深合并进 base（不修改入参）。"""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Config:
    """带点号路径读取的配置对象。"""

    def __init__(self, data: Dict[str, Any], root: str = "", source: str = "default"):
        self.data = data
        self.root = root
        self.source = source

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def project_name(self) -> str:
        return self.get("project.name") or os.path.basename(self.root) or "project"

    def __repr__(self) -> str:  # pragma: no cover
        return "<Config source=%s>" % self.source


def read_raw_config(root: str) -> Dict[str, Any]:
    """读取项目配置文件原文（不做默认值合并），用于契约层判断「用户声明了什么」。"""
    for name in CONFIG_FILENAMES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            try:
                data = yamlmini.load(path)
            except Exception as exc:  # noqa: BLE001 - 配置错误需要可读提示
                raise SystemExit("配置文件解析失败 %s：%s" % (path, exc))
            if not isinstance(data, dict):
                raise SystemExit("配置文件顶层必须是键值映射：%s" % path)
            return data
    return {}


def load_config(root: str) -> Config:
    for name in CONFIG_FILENAMES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            try:
                data = yamlmini.load(path)
            except Exception as exc:  # noqa: BLE001 - 配置错误需要可读提示
                raise SystemExit("配置文件解析失败 %s：%s" % (path, exc))
            if not isinstance(data, dict):
                raise SystemExit("配置文件顶层必须是键值映射：%s" % path)
            return Config(deep_merge(DEFAULT_CONFIG, data), root, name)
    return Config(copy.deepcopy(DEFAULT_CONFIG), root, "default")


def _needs_quote(text: str) -> bool:
    if text == "":
        return True
    special = set(":#{}[]&*?|>%@`!,\"'")
    if text[0] in special or text[-1] in special or text[0] in " \t":
        return True
    return any(ch in special for ch in text)


def _fmt_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False) if _needs_quote(str(value)) else str(value)


def dump_yaml(data: Any, indent: int = 0) -> str:
    """把 dict/list/标量写成 yamlmini 可解析回的最小 YAML。"""
    pad = " " * indent
    out: List[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                if value:
                    out.append("%s%s:" % (pad, key))
                    out.append(dump_yaml(value, indent + 2))
                else:
                    out.append("%s%s: {}" % (pad, key))
            elif isinstance(value, list):
                if value:
                    out.append("%s%s:" % (pad, key))
                    for item in value:
                        if isinstance(item, (dict, list)):
                            # 行内 JSON 形式：yamlmini 支持 {} / [] 流式结构
                            out.append("%s  - %s" % (pad, json.dumps(item, ensure_ascii=False)))
                        else:
                            out.append("%s  - %s" % (pad, _fmt_scalar(item)))
                else:
                    out.append("%s%s: []" % (pad, key))
            else:
                out.append("%s%s: %s" % (pad, key, _fmt_scalar(value)))
    elif isinstance(data, list):
        for item in data:
            out.append("%s- %s" % (pad, _fmt_scalar(item) if not isinstance(item, (dict, list)) else ""))
    else:
        out.append("%s%s" % (pad, _fmt_scalar(data)))
    return "\n".join(out)


HEADER = """# devflow 项目配置
# 由 `devflow init` 生成，修改后请提交到仓库。
# 字段说明见 tools/devflow/../../references/config-reference.md
# 注意：本文件由 yamlmini 解析（零依赖），仅支持 YAML 子集：
#       键值、嵌套映射、列表、行内列表、注释。不支持锚点/别名/多文档。
"""


def write_config(root: str, data: Dict[str, Any], force: bool = False) -> str:
    path = os.path.join(root, "devflow.yaml")
    if os.path.exists(path) and not force:
        return path
    content = HEADER + "\n" + dump_yaml(data) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return path
