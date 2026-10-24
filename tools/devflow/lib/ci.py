"""CI 适配器：把 devflow 门禁接进主流流水线。

核心思路是「平台无关」：
    所有平台最终都调用同一个命令 `devflow gate`（或 `devflow check`），
    流水线 YAML 只是外壳，因此本地能跑通的东西 CI 一定也能跑通。

支持平台：github(GitHub Actions) / gitlab(GitLab CI) / jenkins(Jenkinsfile) / cnb(CNB)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .state import now

PLATFORMS = {
    "github": {
        "template": "ci-github.yml",
        "target": ".github/workflows/devflow.yml",
        "name": "GitHub Actions",
    },
    "gitlab": {
        "template": "ci-gitlab.yml",
        "target": ".gitlab-ci.yml",
        "name": "GitLab CI",
    },
    "jenkins": {
        "template": "ci-jenkins.groovy",
        "target": "Jenkinsfile",
        "name": "Jenkins",
    },
    "cnb": {
        "template": "ci-cnb.yml",
        "target": ".cnb.yml",
        "name": "CNB",
    },
}

EXTRAS = {
    "github": [
        ("repo-github-PULL_REQUEST_TEMPLATE.md", ".github/PULL_REQUEST_TEMPLATE.md"),
        ("repo-github-CODEOWNERS", ".github/CODEOWNERS"),
    ],
    "gitlab": [
        ("repo-gitlab-MR_TEMPLATE.md", ".gitlab/merge_request_templates/Default.md"),
    ],
    "jenkins": [],
    "cnb": [],
}


def available_platforms() -> List[str]:
    return sorted(PLATFORMS)


def _read_template(root: str, cfg, skill_root: str, name: str) -> str:
    search = [
        os.path.join(root, str(cfg.get("paths.state_dir") or ".devflow"), "templates"),
        os.path.join(skill_root, "assets", "templates"),
        os.path.join(root, str(cfg.get("paths.tools") or "tools/devflow"), "templates"),
    ]
    for directory in search:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
    raise FileNotFoundError("找不到 CI 模板：%s" % name)


def render_pipeline(root: str, cfg, skill_root: str, platform: str) -> Dict[str, str]:
    """返回 {相对路径: 内容}（可能包含流水线本体与仓库策略文件）。"""
    meta = PLATFORMS.get(platform)
    if meta is None:
        raise KeyError("未知平台：%s（可选：%s）" % (platform, "、".join(available_platforms())))
    tools_rel = str(cfg.get("paths.tools") or "tools/devflow").replace("\\", "/")
    python = str(cfg.get("ci.python") or "python3")
    ctx = {
        "PROJECT": cfg.project_name(),
        "PYTHON": python,
        "TOOLS": tools_rel,
        "ENTRY": "%s/devflow.py" % tools_rel,
        "STATE_DIR": str(cfg.get("paths.state_dir") or ".devflow"),
        "BRANCH": str(cfg.get("repo.hosting_branch") or "main"),
        "DEVELOP": str(cfg.get("repo.develop_branch") or "develop"),
        "STATUS_FILE": str(cfg.get("ci.status_file") or ".devflow/ci-status.json"),
    }
    outputs: Dict[str, str] = {}
    for template_name, target in [(meta["template"], meta["target"])] + EXTRAS.get(platform, []):
        content = _read_template(root, cfg, skill_root, template_name)
        for key, value in ctx.items():
            content = content.replace("{{%s}}" % key, value)
        outputs[target] = content
    return outputs


def emit(root: str, cfg, skill_root: str, platform: Optional[str] = None,
         out_dir: str = "", overwrite: bool = False) -> Dict[str, str]:
    platform = (platform or str(cfg.get("platform.ci") or "none")).lower()
    if platform in ("", "none"):
        raise ValueError("未指定流水线平台，请用 --platform 或配置 devflow.yaml#platform.ci")
    rendered = render_pipeline(root, cfg, skill_root, platform)
    written: Dict[str, str] = {}
    for rel, content in rendered.items():
        target_rel = "%s/%s" % (out_dir.rstrip("/"), rel) if out_dir and out_dir != "." else rel
        path = os.path.join(root, target_rel)
        if os.path.exists(path) and not overwrite:
            written[target_rel] = "skipped(existing)"
            continue
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        written[target_rel] = "written"
    return written


def record_status(root: str, cfg, result: str, **extra: Any) -> Dict[str, Any]:
    """流水线作业结束后把结果写入 ci-status.json，供 `ci.last_run` 门禁读取。"""
    rel = str(cfg.get("ci.status_file") or ".devflow/ci-status.json")
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    allowed = ("success", "failed", "cancelled", "running")
    status = str(result or "").lower()
    if status not in allowed:
        raise ValueError("非法流水线结果：%s（可选：%s）" % (result, "/".join(allowed)))
    data = {"status": status, "updated_at": now()}
    data.update(extra)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return data
