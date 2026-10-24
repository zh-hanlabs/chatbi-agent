"""契约层：把「阶段 / 产出物 / 规则」从 Python 代码抽到声明式配置。

分层覆盖（后者覆盖前者）：

    assets/profiles/<基线>.yaml      SKILL 内置基线（standard / minimal / strict / skeleton）
      └─ extends 可递归继承
    <项目>/.devflow/profiles/*.yaml  团队级复用（可选，且可覆盖同名内置基线）
    devflow.yaml                     本项目的定制（extends + phases/artifacts/rules 增量）

设计意图：**框架与实现分离**。
引擎只负责「按契约执行」，内置基线只是「一份可以整体换掉的默认实现」；
项目可以把阶段、产出物类型、检查规则全部按真实需求重新声明。

旧版扁平配置（phases.enabled / rules.severity / artifacts.optional /
test.min_coverage / repo.branch_patterns ...）通过 legacy 适配层继续生效，
升级不会破坏既有项目。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import yamlmini

BUILTIN_PROFILES = ("standard", "minimal", "strict", "skeleton", "none")
DEFAULT_PROFILE = "standard"
MAX_EXTENDS_DEPTH = 6


@dataclass
class PhaseSpec:
    id: str
    seq: float = 0
    name: str = ""
    goal: str = ""
    artifacts: List[str] = field(default_factory=list)
    entry: List[str] = field(default_factory=list)
    exit: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)

    # 兼容旧字段命名（phases.py 原先使用 entry_rules / exit_rules）
    @property
    def entry_rules(self) -> List[str]:
        return self.entry

    @property
    def exit_rules(self) -> List[str]:
        return self.exit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "seq": self.seq, "name": self.name, "goal": self.goal,
            "artifacts": list(self.artifacts), "entry": list(self.entry),
            "exit": list(self.exit), "next_actions": list(self.next_actions),
        }


@dataclass
class ArtifactSpec:
    kind: str
    phase: str = ""
    dir_key: str = ""
    dir: str = ""            # dir_key 缺省时的直接路径
    prefix: str = ""
    template: str = ""
    label: str = ""
    id_width: int = 3
    optional: bool = False
    required_fields: List[str] = field(default_factory=list)
    required_sections: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "kind": self.kind, "phase": self.phase, "prefix": self.prefix,
            "label": self.label, "id_width": self.id_width, "optional": self.optional,
            "required_fields": list(self.required_fields),
            "required_sections": list(self.required_sections),
        }
        if self.dir_key:
            data["dir_key"] = self.dir_key
        if self.dir:
            data["dir"] = self.dir
        if self.template:
            data["template"] = self.template
        return data


@dataclass
class RuleRef:
    id: str
    title: str = ""
    category: str = "custom"
    severity: str = ""       # 空 = 沿用规则自身默认
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    checks: List[Dict[str, Any]] = field(default_factory=list)   # 非空即为 DSL 自定义规则
    when: List[Dict[str, Any]] = field(default_factory=list)     # 前置条件，全部通过才执行
    source: str = "builtin"  # builtin | dsl | profile | project

    @property
    def is_dsl(self) -> bool:
        return bool(self.checks)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "severity": self.severity,
            "enabled": self.enabled,
            "source": self.source,
        }
        if self.title:
            data["title"] = self.title
        if self.category != "custom":
            data["category"] = self.category
        if self.params:
            data["params"] = self.params
        if self.checks:
            data["checks"] = self.checks
        if self.when:
            data["when"] = self.when
        return data


class Contract:
    def __init__(self) -> None:
        self.phases: List[PhaseSpec] = []
        self.artifacts: Dict[str, ArtifactSpec] = {}
        self.rules: Dict[str, RuleRef] = {}
        self.chain: List[str] = []          # 生效的 profile 链（基础 → 具体）
        self.notes: List[str] = []          # 契约自检提示（非致命）
        self.config_patch: Dict[str, Any] = {}   # profile 携带的配置基线（阈值、模式等）

    # ---- 阶段 ----
    def phase(self, pid: str) -> Optional[PhaseSpec]:
        for p in self.phases:
            if p.id == pid:
                return p
        return None

    def phase_ids(self) -> List[str]:
        return [p.id for p in self.phases]

    def previous_phase(self, pid: str) -> Optional[PhaseSpec]:
        index = next((i for i, p in enumerate(self.phases) if p.id == pid), None)
        if index is None or index == 0:
            return None
        return self.phases[index - 1]

    def next_phase(self, pid: str) -> Optional[PhaseSpec]:
        index = next((i for i, p in enumerate(self.phases) if p.id == pid), None)
        if index is None or index + 1 >= len(self.phases):
            return None
        return self.phases[index + 1]

    def rule_ids_for(self, pid: str, scope: str) -> List[str]:
        phase = self.phase(pid)
        if phase is None:
            return []
        return list(phase.entry if scope == "entry" else phase.exit)

    def all_rule_ids(self) -> List[str]:
        out: List[str] = []
        for phase in self.phases:
            for rid in list(phase.entry) + list(phase.exit):
                if rid not in out:
                    out.append(rid)
        return out

    # ---- 产出物 ----
    def artifact(self, kind: str) -> Optional[ArtifactSpec]:
        return self.artifacts.get(kind)

    def kinds(self) -> List[str]:
        return list(self.artifacts)

    def kinds_of_phase(self, pid: str) -> List[str]:
        return [k for k, s in self.artifacts.items() if s.phase == pid]

    def required_kinds_of_phase(self, pid: str) -> List[str]:
        return [k for k, s in self.artifacts.items() if s.phase == pid and not s.optional]

    def rule(self, rid: str) -> Optional[RuleRef]:
        return self.rules.get(rid)

    def unknown_rules(self) -> List[str]:
        """阶段引用了、但契约与内置规则库里都没有的规则 id。"""
        known = set(self.rules) | _BUILTIN_RULE_IDS()
        return [rid for rid in self.all_rule_ids() if rid not in known]

    def validate(self) -> List[str]:
        """契约自检，返回提示列表（不抛异常）。"""
        builtin = _BUILTIN_RULE_IDS()
        notes: List[str] = []
        seen_phase: Dict[str, int] = {}
        for index, phase in enumerate(self.phases):
            if phase.id in seen_phase:
                notes.append("阶段 id 重复：%s（第 %d 与第 %d 项）" % (phase.id, seen_phase[phase.id] + 1, index + 1))
            seen_phase[phase.id] = index
            for rid in list(phase.entry) + list(phase.exit):
                if rid not in self.rules and rid not in builtin:
                    notes.append("阶段 %s 引用了未定义的规则：%s（既非内置规则，也没有 checks 定义）" % (phase.id, rid))
            for kind in phase.artifacts:
                if kind not in self.artifacts:
                    notes.append("阶段 %s 引用了未定义的产出物类型：%s" % (phase.id, kind))
        for kind, spec in self.artifacts.items():
            if spec.phase and spec.phase not in seen_phase:
                notes.append("产出物类型 %s 的 phase=%s 不是已定义的阶段" % (kind, spec.phase))
            if not spec.prefix:
                notes.append("产出物类型 %s 缺少 prefix，编号无法生成" % kind)
        for rid, ref in self.rules.items():
            if ref.is_dsl:
                for check in ref.checks:
                    if not check.get("type"):
                        notes.append("DSL 规则 %s 的某个 check 缺少 type" % rid)
            elif rid not in builtin:
                notes.append("规则 %s 既非内置规则也没有 checks，永远不会被执行" % rid)
        self.notes = notes
        return notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extends_chain": list(self.chain),
            "phases": [p.to_dict() for p in self.phases],
            "artifacts": [s.to_dict() for s in self.artifacts.values()],
            "rules": [r.to_dict() for r in self.rules.values()],
            "notes": list(self.notes),
        }


# ------------------------------------------------------------------ 内置规则 id（延迟获取，避免循环导入）
def _BUILTIN_RULE_IDS() -> set:
    from . import gates as G
    return set(G.RULES)


# ------------------------------------------------------------------ 解析与合并
def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _phase_from_dict(data: Dict[str, Any], index: int) -> PhaseSpec:
    seq = data.get("seq")
    try:
        seq = float(seq) if seq is not None else float(index + 1)
    except (TypeError, ValueError):
        seq = float(index + 1)
    return PhaseSpec(
        id=str(data.get("id", "")).strip(),
        seq=seq,
        name=str(data.get("name", "")).strip(),
        goal=str(data.get("goal", "")).strip(),
        artifacts=[str(k) for k in _as_list(data.get("artifacts"))],
        entry=[str(r) for r in _as_list(data.get("entry"))],
        exit=[str(r) for r in _as_list(data.get("exit"))],
        next_actions=[str(a) for a in _as_list(data.get("next_actions"))],
    )


def _artifact_from_dict(data: Dict[str, Any]) -> Optional[ArtifactSpec]:
    kind = str(data.get("kind", "")).strip()
    if not kind:
        return None
    width = data.get("id_width", 3)
    try:
        width = int(width)
    except (TypeError, ValueError):
        width = 3
    return ArtifactSpec(
        kind=kind,
        phase=str(data.get("phase", "")).strip(),
        dir_key=str(data.get("dir_key", "")).strip(),
        dir=str(data.get("dir", "")).strip(),
        prefix=str(data.get("prefix", "")).strip(),
        template=str(data.get("template", "")).strip(),
        label=str(data.get("label", "")).strip() or kind,
        id_width=width,
        optional=bool(data.get("optional", False)),
        required_fields=[str(f) for f in _as_list(data.get("required_fields"))],
        required_sections=[str(s) for s in _as_list(data.get("required_sections"))],
    )


def _rule_from_dict(data: Dict[str, Any], source: str) -> Optional[RuleRef]:
    rid = str(data.get("id", "")).strip()
    if not rid:
        return None
    params = data.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    return RuleRef(
        id=rid,
        title=str(data.get("title", "")).strip(),
        category=str(data.get("category", "custom")).strip() or "custom",
        severity=str(data.get("severity", "")).strip().lower(),
        enabled=bool(data.get("enabled", True)),
        params=dict(params),
        checks=[dict(c) for c in _as_list(data.get("checks")) if isinstance(c, dict)],
        when=[dict(c) for c in _as_list(data.get("when")) if isinstance(c, dict)],
        source=source,
    )


def _merge_phase(base: Optional[PhaseSpec], data: Dict[str, Any], index: int) -> PhaseSpec:
    incoming = _phase_from_dict(data, index)
    if base is None:
        return incoming
    merged = PhaseSpec(
        id=base.id,
        seq=incoming.seq if data.get("seq") is not None else base.seq,
        name=incoming.name or base.name,
        goal=incoming.goal or base.goal,
        artifacts=incoming.artifacts or base.artifacts,
        entry=incoming.entry or base.entry,
        exit=incoming.exit or base.exit,
        next_actions=incoming.next_actions or base.next_actions,
    )
    return merged


def _merge_artifact(base: Optional[ArtifactSpec], data: Dict[str, Any]) -> Optional[ArtifactSpec]:
    incoming = _artifact_from_dict(data)
    if incoming is None:
        return base
    if base is None:
        return incoming
    return ArtifactSpec(
        kind=base.kind,
        phase=incoming.phase or base.phase,
        dir_key=incoming.dir_key or base.dir_key,
        dir=incoming.dir or base.dir,
        prefix=incoming.prefix or base.prefix,
        template=incoming.template or base.template,
        label=incoming.label if incoming.label != base.kind else base.label,
        id_width=incoming.id_width if data.get("id_width") is not None else base.id_width,
        optional=bool(data["optional"]) if "optional" in data else base.optional,
        required_fields=incoming.required_fields or base.required_fields,
        required_sections=incoming.required_sections or base.required_sections,
    )


def _merge_rule(base: Optional[RuleRef], data: Dict[str, Any], source: str) -> Optional[RuleRef]:
    incoming = _rule_from_dict(data, source)
    if incoming is None:
        return base
    if base is None:
        return incoming
    params = dict(base.params)
    params.update(incoming.params)
    return RuleRef(
        id=base.id,
        title=incoming.title or base.title,
        category=incoming.category if incoming.category != "custom" else base.category,
        severity=incoming.severity or base.severity,
        enabled=bool(data["enabled"]) if "enabled" in data else base.enabled,
        params=params,
        checks=incoming.checks or base.checks,
        when=incoming.when or base.when,
        # 项目里出现 checks 就从 builtin 变成 dsl
        source=("dsl" if incoming.checks else (source if source == "project" else base.source)),
    )


def _apply_layer(contract: Contract, layer: Dict[str, Any], source: str) -> None:
    phases: Dict[str, PhaseSpec] = {p.id: p for p in contract.phases}
    order: List[str] = [p.id for p in contract.phases]
    for index, item in enumerate(_as_list(layer.get("phases"))):
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", "")).strip()
        if not pid:
            continue
        if item.get("enabled") is False:      # 显式裁掉某个阶段
            phases.pop(pid, None)
            if pid in order:
                order.remove(pid)
            continue
        if pid not in phases:
            order.append(pid)
        phases[pid] = _merge_phase(phases.get(pid), item, index)

    for item in _as_list(layer.get("artifacts")):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        if not kind:
            continue
        if item.get("enabled") is False:      # 显式裁掉某个产出物类型
            contract.artifacts.pop(kind, None)
            continue
        merged = _merge_artifact(contract.artifacts.get(kind), item)
        if merged is not None:
            contract.artifacts[kind] = merged

    for item in _as_list(layer.get("rules")):
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id", "")).strip()
        if not rid:
            continue
        merged = _merge_rule(contract.rules.get(rid), item, source)
        if merged is not None:
            contract.rules[rid] = merged

    contract.phases = [phases[pid] for pid in order if pid in phases]
    contract.phases.sort(key=lambda p: p.seq)


# ------------------------------------------------------------------ profile 解析
def profile_dirs(root: str, cfg, skill_root: str) -> List[str]:
    out = [
        os.path.join(root, str(cfg.get("paths.state_dir") or ".devflow"), "profiles"),
        os.path.join(root, str(cfg.get("paths.tools") or "tools/devflow"), "profiles"),
        os.path.join(skill_root, "assets", "profiles"),
    ]
    seen: List[str] = []
    for path in out:
        real = os.path.abspath(path)
        if real not in seen:
            seen.append(real)
    return seen


def _find_profile(name: str, root: str, cfg, skill_root: str) -> Optional[str]:
    for directory in profile_dirs(root, cfg, skill_root):
        path = os.path.join(directory, "%s.yaml" % name)
        if os.path.isfile(path):
            return path
        path = os.path.join(directory, "%s.yml" % name)
        if os.path.isfile(path):
            return path
    return None


def _resolve_chain(name: str, root: str, cfg, skill_root: str,
                   visited: Optional[set] = None, depth: int = 0) -> Tuple[List[Dict[str, Any]], List[str]]:
    """解析一条 extends 链，返回 (层列表, 链名称列表)，基础在前。"""
    visited = visited if visited is not None else set()
    layers: List[Dict[str, Any]] = []
    names: List[str] = []
    if depth > MAX_EXTENDS_DEPTH or not name or name == "none":
        return layers, names
    path = _find_profile(name, root, cfg, skill_root)
    if path is None:
        # 也可能是相对/绝对路径指向的自定义 profile
        candidate = name if os.path.isabs(name) else os.path.join(root, name)
        if not os.path.isfile(candidate):
            return layers, names
        path = candidate
    real = os.path.abspath(path)
    if real in visited:
        return layers, names
    visited.add(real)
    try:
        data = yamlmini.load(path)
    except Exception:  # noqa: BLE001 - 契约文件错误由 contract lint 报告
        return layers, names
    if not isinstance(data, dict):
        return layers, names
    parents = _as_list(data.get("extends")) if "extends" in data else []
    for parent in parents:
        sub_layers, sub_names = _resolve_chain(str(parent), root, cfg, skill_root, visited, depth + 1)
        layers.extend(sub_layers)
        names.extend(sub_names)
    data = dict(data)
    data.pop("extends", None)
    layers.append(data)
    names.append(name)
    return layers, names


# ------------------------------------------------------------------ legacy 适配
LEGACY_PARAM_MAP: Dict[str, Dict[str, str]] = {
    "test.coverage": {"min": "test.min_coverage"},
    "test.cases": {"min_cases": "test.min_cases"},
    "repo.commit": {"types": "repo.commit_types"},
    "repo.branch": {"patterns": "repo.branch_patterns"},
    "repo.large_files": {"max_mb": "repo.max_file_mb"},
    "repo.secrets": {"patterns": "repo.secret_patterns", "ignore": "repo.ignore_paths"},
    "review.approvals": {"min_reviewers": "review.min_reviewers"},
    "doc.approval": {"min_reviewers": "review.min_reviewers"},
    "release.version": {"require_tag": "release.require_tag", "tag_prefix": "release.tag_prefix"},
}


def _apply_legacy(contract: Contract, raw: Dict[str, Any], cfg) -> None:
    """把旧版扁平字段映射到契约，保证既有项目升级后行为不变。"""
    raw_phases = raw.get("phases")
    if isinstance(raw_phases, dict):
        enabled = [str(x) for x in _as_list(raw_phases.get("enabled"))]
        if enabled:
            contract.phases = [p for p in contract.phases if p.id in enabled]
    raw_artifacts = raw.get("artifacts")
    if isinstance(raw_artifacts, dict):
        for kind in _as_list(raw_artifacts.get("optional")):
            spec = contract.artifacts.get(str(kind))
            if spec is not None:
                spec.optional = True
    raw_rules = raw.get("rules")
    if isinstance(raw_rules, dict):
        for rid, severity in (raw_rules.get("severity") or {}).items():
            ref = contract.rules.get(str(rid))
            if ref is None:
                ref = RuleRef(id=str(rid), source="builtin")
                contract.rules[str(rid)] = ref
            ref.severity = str(severity).strip().lower()
        for rid in _as_list(raw_rules.get("disabled")):
            ref = contract.rules.get(str(rid))
            if ref is None:
                contract.rules[str(rid)] = RuleRef(id=str(rid), source="builtin")
            contract.rules[str(rid)].enabled = False
    for rid, mapping in LEGACY_PARAM_MAP.items():
        ref = contract.rules.get(rid)
        if ref is None:
            continue
        for param_key, cfg_path in mapping.items():
            if param_key in ref.params:
                continue
            value = cfg.get(cfg_path)
            if value is not None:
                ref.params[param_key] = value


# ------------------------------------------------------------------ 入口
def _builtin_contract() -> Contract:
    """profile 文件缺失时的兜底：直接由 Python 内置常量构造。"""
    from . import artifacts as A
    from . import gates as G
    from . import phases as P

    contract = Contract()
    contract.chain = ["(builtin-fallback)"]
    for phase in P.BUILTIN_PHASES:
        contract.phases.append(PhaseSpec(
            id=phase.id, seq=float(phase.seq), name=phase.name, goal=phase.goal,
            artifacts=list(phase.artifacts), entry=list(phase.entry_rules),
            exit=list(phase.exit_rules), next_actions=list(phase.next_actions),
        ))
    for kind, spec in A.BUILTIN_ARTIFACTS.items():
        contract.artifacts[kind] = ArtifactSpec(
            kind=kind, phase=spec.phase, dir_key=spec.dir_key, prefix=spec.prefix,
            template=spec.template, label=spec.label, id_width=spec.id_width,
            required_fields=list(spec.required_fields),
            required_sections=list(spec.required_sections),
        )
    for rid, rule in G.RULES.items():
        contract.rules[rid] = RuleRef(id=rid, title=rule.title, category=rule.category,
                                      severity=rule.severity, source="builtin")
    return contract


_ACTIVE: Optional[Contract] = None


def set_active(contract: Contract) -> None:
    global _ACTIVE
    _ACTIVE = contract


def get_active() -> Optional[Contract]:
    return _ACTIVE


def load_contract(root: str, cfg, skill_root: str, raw: Optional[Dict[str, Any]] = None,
                  apply_legacy: bool = True) -> Contract:
    """加载并合并生效契约。raw 为 devflow.yaml 原文（不含默认值合并）。"""
    raw = raw if raw is not None else {}
    has_profile_file = any(
        os.path.isfile(os.path.join(d, "%s.yaml" % name))
        for name in BUILTIN_PROFILES if name != "none"
        for d in profile_dirs(root, cfg, skill_root)
    )
    if not has_profile_file:
        contract = _builtin_contract()
    else:
        contract = Contract()

    extends = raw.get("extends")
    if extends is None:
        extends = DEFAULT_PROFILE
    layers: List[Dict[str, Any]] = []
    names: List[str] = []
    for name in _as_list(extends):
        sub_layers, sub_names = _resolve_chain(str(name), root, cfg, skill_root)
        layers.extend(sub_layers)
        names.extend(sub_names)
    contract.chain = names
    for layer in layers:
        _apply_layer(contract, layer, "profile")
        patch = layer.get("config")
        if isinstance(patch, dict):
            contract.config_patch = _deep_merge(contract.config_patch, patch)
    _apply_layer(contract, raw, "project")
    if apply_legacy:
        _apply_legacy(contract, raw, cfg)
    contract.validate()
    return contract


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    import copy

    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def bootstrap(root: str, skill_root: str):
    """一次性拿到「最终配置 + 生效契约」，顺序保证 profile 基线 < 项目定制。

    返回 (Config, Contract)。这是所有命令的标准入口。
    """
    from . import config as C

    raw = C.read_raw_config(root)
    probe = C.Config(_deep_merge(C.DEFAULT_CONFIG, raw), root, "devflow.yaml" if raw else "default")
    contract = load_contract(root, probe, skill_root, raw, apply_legacy=False)
    data = _deep_merge(C.DEFAULT_CONFIG, contract.config_patch)
    data = _deep_merge(data, raw)
    cfg = C.Config(data, root, "devflow.yaml" if raw else "default")
    _apply_legacy(contract, raw, cfg)
    contract.validate()
    set_active(contract)
    return cfg, contract
