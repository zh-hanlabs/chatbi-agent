"""阶段契约。

**这份文件现在是「内置默认实现」，不是唯一实现。**
生效的阶段列表来自契约（`lib/contract.py`）：

    assets/profiles/standard.yaml  →  devflow.yaml 的 phases: 增量

本模块保留 BUILTIN_PHASES 作为兜底（profile 文件缺失时使用），
并把所有查询函数改为「优先读生效契约」。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .contract import PhaseSpec, get_active, BUILTIN_PROFILES  # noqa: F401

BUILTIN_PHASES: List[PhaseSpec] = [
    PhaseSpec(
        id="intake", seq=1, name="需求立项",
        goal="把模糊诉求收敛成可验收、可排优先级、有明确负责人的需求条目",
        artifacts=["requirement"],
        entry=[],
        exit=[
            "doc.exists", "doc.frontmatter", "doc.sections", "doc.placeholder",
            "doc.approval", "doc.review_record", "doc.index",
        ],
        next_actions=[
            "补齐缺失的需求字段后再次运行 `devflow check`",
            "运行 `devflow phase enter --to design` 进入方案设计",
        ],
    ),
    PhaseSpec(
        id="design", seq=2, name="方案设计",
        goal="给出可落地的技术方案、关键架构决策与接口/数据契约，并完成设计评审",
        artifacts=["design", "adr"],
        entry=["phase.prev_completed", "phase.entry_docs"],
        exit=[
            "doc.exists", "doc.frontmatter", "doc.sections", "doc.placeholder",
            "doc.approval", "doc.review_record", "design.contract", "doc.index",
        ],
        next_actions=[
            "用 `devflow new adr --title \"为何选择 X 而非 Y\"` 固化关键取舍",
            "运行 `devflow phase enter --to plan` 进入排期",
        ],
    ),
    PhaseSpec(
        id="plan", seq=3, name="排期计划",
        goal="把方案拆成有负责人、有估时、有依赖与里程碑的任务（WBS），形成可跟踪的计划",
        artifacts=["plan"],
        entry=["phase.prev_completed", "phase.entry_docs", "task.planned"],
        exit=[
            "doc.exists", "doc.frontmatter", "doc.sections", "doc.placeholder",
            "task.planned", "task.schedule", "task.ownership", "plan.milestones", "doc.index",
        ],
        next_actions=[
            "用 `devflow task add` 补齐遗漏任务及其 owner/估时/截止日",
            "运行 `devflow phase enter --to develop` 开始开发",
        ],
    ),
    PhaseSpec(
        id="develop", seq=4, name="开发执行",
        goal="按分支与提交规范完成编码、自测和 PR 提交，满足合入门禁",
        artifacts=[],
        entry=["phase.prev_completed", "task.planned", "repo.branch"],
        exit=[
            "repo.branch", "repo.commit", "repo.secrets", "repo.large_files",
            "repo.readme", "repo.tree_clean", "ci.config", "task.in_progress",
        ],
        next_actions=[
            "创建符合规范的分支与 PR：`feature/<需求号>-<简述>`",
            "运行 `devflow new review --title \"XXX 代码评审\"` 进入评审阶段",
        ],
    ),
    PhaseSpec(
        id="review", seq=5, name="代码评审",
        goal="通过结构化 checklist 完成代码评审，确保所有意见闭环并有足够 approve",
        artifacts=["review"],
        entry=["phase.prev_completed", "phase.entry_docs"],
        exit=[
            "doc.exists", "doc.frontmatter", "doc.sections", "doc.placeholder",
            "review.approvals", "review.checklist", "review.comments_resolved", "doc.index",
        ],
        next_actions=[
            "让评审人执行 `devflow approve --target <评审单号> --by <姓名>`",
            "运行 `devflow phase enter --to test` 进入测试验证",
        ],
    ),
    PhaseSpec(
        id="test", seq=6, name="测试验证",
        goal="以测试计划驱动验证，覆盖功能/边界/异常/性能，缺陷分级清零后方可发布",
        artifacts=["testplan"],
        entry=["phase.prev_completed", "phase.entry_docs"],
        exit=[
            "doc.exists", "doc.frontmatter", "doc.sections", "doc.placeholder",
            "test.cases", "test.results", "test.coverage", "test.bug_triage",
            "ci.last_run", "doc.index",
        ],
        next_actions=[
            "补齐 P0/P1 用例执行结果，跑出覆盖率并写入 .devflow/coverage.json",
            "运行 `devflow phase enter --to release` 进入发布",
        ],
    ),
    PhaseSpec(
        id="release", seq=7, name="发布部署",
        goal="按发布计划灰度上线，流水线全绿、可观测到位、回滚方案可用",
        artifacts=["releaseplan"],
        entry=["phase.prev_completed", "phase.entry_docs", "task.blocking_done"],
        exit=[
            "doc.exists", "doc.frontmatter", "doc.sections", "doc.placeholder",
            "doc.approval", "release.changelog", "release.version", "release.rollback",
            "release.env_ready", "ci.last_run", "task.blocking_done", "doc.index",
        ],
        next_actions=[
            "更新 CHANGELOG.md 并打 tag：`git tag vX.Y.Z`",
            "运行 `devflow phase enter --to retro` 进入复盘",
        ],
    ),
    PhaseSpec(
        id="retro", seq=8, name="复盘归档",
        goal="用数据复盘目标达成情况，沉淀改进项并回流到需求池",
        artifacts=["retro"],
        entry=["phase.prev_completed", "phase.entry_docs"],
        exit=[
            "doc.exists", "doc.frontmatter", "doc.sections", "doc.placeholder",
            "retro.metrics", "retro.actions", "doc.index",
        ],
        next_actions=[
            "把改进项注册成任务：`devflow task add --title \"...\" --tag retro`",
            "运行 `devflow archive` 归档本次迭代",
        ],
    ),
]

PHASE_BY_ID: Dict[str, PhaseSpec] = {p.id: p for p in BUILTIN_PHASES}


def enabled_phases(cfg=None) -> List[PhaseSpec]:
    """生效的阶段列表（按 seq 排序）。"""
    contract = get_active()
    if contract is not None:
        return list(contract.phases)
    enabled = (cfg.get("phases.enabled") if cfg else None) or [p.id for p in BUILTIN_PHASES]
    return [p for p in BUILTIN_PHASES if p.id in enabled]


def get_phase(pid: str) -> Optional[PhaseSpec]:
    contract = get_active()
    if contract is not None:
        return contract.phase(pid)
    return PHASE_BY_ID.get(pid)


def previous_phase(pid: str, cfg=None) -> Optional[PhaseSpec]:
    contract = get_active()
    if contract is not None:
        return contract.previous_phase(pid)
    phases = enabled_phases(cfg)
    index = next((i for i, p in enumerate(phases) if p.id == pid), None)
    if index is None or index == 0:
        return None
    return phases[index - 1]


def next_phase(pid: str, cfg=None) -> Optional[PhaseSpec]:
    contract = get_active()
    if contract is not None:
        return contract.next_phase(pid)
    phases = enabled_phases(cfg)
    index = next((i for i, p in enumerate(phases) if p.id == pid), None)
    if index is None or index + 1 >= len(phases):
        return None
    return phases[index + 1]


def artifacts_of(phase_id: str) -> List[str]:
    phase = get_phase(phase_id)
    return list(phase.artifacts) if phase else []
