"""产出物（文档）类型契约：编号规则、目录、front-matter 必填字段、正文必填小节。

**这份文件现在是「内置默认实现」，不是唯一实现。**
生效的类型定义来自契约（`lib/contract.py`）：

    assets/profiles/standard.yaml  →  devflow.yaml 的 artifacts: 增量

项目可以声明自己的类型（如「数据迁移方案」「UAT 验收单」「安全评审记录」），
只要写清 prefix / 目录 / 必填字段 / 必填小节即可，模板可由引擎自动生成。

front-matter 必填字段用于 machine-checkable 的准出门禁；
正文必填小节用于防止「模板直接过评审」这种形式主义。
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from .contract import ArtifactSpec, get_active
from . import yamlmini  # noqa: F401 - 向后兼容：本模块早期对外暴露过 yamlmini

BUILTIN_ARTIFACTS: Dict[str, ArtifactSpec] = {
    "requirement": ArtifactSpec(
        kind="requirement", phase="intake", dir_key="requirements", prefix="REQ",
        template="requirement.md", label="需求说明书",
        required_fields=["id", "title", "status", "priority", "owner", "created", "source"],
        required_sections=["背景与问题", "目标与非目标", "用户故事", "验收标准 (AC)",
                           "范围与依赖", "风险与对策", "优先级说明", "评审记录"],
    ),
    "design": ArtifactSpec(
        kind="design", phase="design", dir_key="design", prefix="DESIGN",
        template="design.md", label="技术方案设计",
        required_fields=["id", "title", "status", "owner", "created", "related_requirement"],
        required_sections=["总体方案", "详细设计", "接口契约", "数据模型", "容量与性能",
                           "异常处理与降级", "安全与合规", "可观测性", "测试策略", "评审记录"],
    ),
    "adr": ArtifactSpec(
        kind="adr", phase="design", dir_key="adr", prefix="ADR",
        template="adr.md", label="架构决策记录",
        required_fields=["id", "title", "status", "decision_date", "owner"],
        required_sections=["背景", "决策", "候选方案对比", "影响", "遵循性检查"],
    ),
    "plan": ArtifactSpec(
        kind="plan", phase="plan", dir_key="plan", prefix="PLAN",
        template="plan.md", label="排期计划",
        required_fields=["id", "title", "status", "start_date", "target_date", "owner"],
        required_sections=["迭代目标", "WBS 任务清单", "里程碑", "人力资源与负载",
                           "关键依赖", "风险与缓冲", "计划评审"],
    ),
    "review": ArtifactSpec(
        kind="review", phase="review", dir_key="review", prefix="REVIEW",
        template="review.md", label="代码评审记录",
        required_fields=["id", "title", "status", "owner", "reviewers", "created", "comments_resolved"],
        required_sections=["变更清单", "评审 checklist", "评审意见", "遗留问题与跟进"],
    ),
    "testplan": ArtifactSpec(
        kind="testplan", phase="test", dir_key="test", prefix="TEST",
        template="test-plan.md", label="测试计划",
        required_fields=["id", "title", "status", "owner", "created", "env"],
        required_sections=["测试范围", "测试环境", "功能用例", "边界与异常用例", "性能与稳定性",
                           "回归策略", "出口准则", "执行结果", "缺陷跟踪"],
    ),
    "releaseplan": ArtifactSpec(
        kind="releaseplan", phase="release", dir_key="release", prefix="RELEASE",
        template="release-plan.md", label="发布计划",
        required_fields=["id", "title", "status", "owner", "version", "release_date",
                         "rollback_ready", "env_ready"],
        required_sections=["发布内容", "前置检查", "发布步骤", "灰度与观测", "回滚方案",
                           "发布后验证", "发布记录"],
    ),
    "retro": ArtifactSpec(
        kind="retro", phase="retro", dir_key="retro", prefix="RETRO",
        template="retro.md", label="复盘报告",
        required_fields=["id", "title", "status", "owner", "retro_date", "iteration"],
        required_sections=["目标达成情况", "指标回顾", "做得好的地方", "待改进项", "结论与后续动作"],
    ),
}

# 命令行简写别名；自定义类型自动获得与 kind 同名的别名
KIND_ALIASES: Dict[str, str] = {
    "req": "requirement", "requirement": "requirement",
    "design": "design", "adr": "adr", "plan": "plan",
    "review": "review", "test": "testplan", "testplan": "testplan",
    "release": "releaseplan", "releaseplan": "releaseplan",
    "retro": "retro", "retrospective": "retro",
}


def _kinds() -> Dict[str, ArtifactSpec]:
    contract = get_active()
    if contract is not None:
        return contract.artifacts
    return BUILTIN_ARTIFACTS


def resolve_kind(kind: str) -> str:
    key = (kind or "").lower().strip()
    if key in KIND_ALIASES:
        return KIND_ALIASES[key]
    available = _kinds()
    if key in available:                      # 自定义类型直接用 kind
        return key
    raise KeyError("未知产出物类型：%s（可选：%s）" % (
        kind, "、".join(sorted(set(KIND_ALIASES) | set(available)))))


def spec(kind: str) -> ArtifactSpec:
    resolved = resolve_kind(kind)
    try:
        return _kinds()[resolved]
    except KeyError:
        raise KeyError("契约中未定义产出物类型：%s" % kind)


def all_kinds() -> List[str]:
    return list(_kinds())


def kinds_of_phase(phase_id: str) -> List[str]:
    contract = get_active()
    if contract is not None:
        return contract.kinds_of_phase(phase_id)
    return [k for k, s in BUILTIN_ARTIFACTS.items() if s.phase == phase_id]


def required_kinds_of_phase(phase_id: str, cfg=None) -> List[str]:
    """某阶段「必需」的产出物类型（排除 optional）。"""
    contract = get_active()
    if contract is not None:
        return contract.required_kinds_of_phase(phase_id)
    optional = list(cfg.get("artifacts.optional") or []) if cfg else []
    return [k for k, s in BUILTIN_ARTIFACTS.items()
            if s.phase == phase_id and k not in optional]


def dir_of(root: str, cfg, kind: str) -> str:
    resolved = resolve_kind(kind)
    s = _kinds()[resolved]
    if s.dir_key:
        sub = cfg.get("paths.%s" % s.dir_key) or s.dir_key
    elif s.dir:
        sub = s.dir
    else:
        sub = "docs/%s" % resolved
    return os.path.join(root, str(sub))


def _id_pattern(prefix: str, width: int) -> re.Pattern:
    return re.compile(r"^%s-(\d{%d,})" % (re.escape(prefix), width))


def next_id(root: str, cfg, kind: str) -> str:
    resolved = resolve_kind(kind)
    s = _kinds()[resolved]
    directory = dir_of(root, cfg, resolved)
    pattern = _id_pattern(s.prefix, s.id_width)
    max_seq = 0
    if os.path.isdir(directory):
        for name in os.listdir(directory):
            match = pattern.match(name)
            if match:
                max_seq = max(max_seq, int(match.group(1)))
    return "%s-%s" % (s.prefix, str(max_seq + 1).zfill(s.id_width))


def slugify(text: str, fallback: str = "item") -> str:
    """生成 ASCII 安全的文件片段；中文标题会退化为空，由调用方指定 fallback。"""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:48] or fallback


def list_files(root: str, cfg, kind: str) -> List[str]:
    """列出该类型在磁盘上的全部文档（相对仓库根目录）。"""
    resolved = resolve_kind(kind)
    directory = dir_of(root, cfg, resolved)
    if not os.path.isdir(directory):
        return []
    prefix = _kinds()[resolved].prefix
    rel_root = os.path.relpath(directory, root)
    files = []
    for name in sorted(os.listdir(directory)):
        if name.startswith(prefix) and name.endswith(".md"):
            files.append(os.path.join(rel_root, name).replace("\\", "/"))
    return files


def find_all(root: str, cfg) -> Dict[str, List[str]]:
    return {kind: list_files(root, cfg, kind) for kind in all_kinds()}
