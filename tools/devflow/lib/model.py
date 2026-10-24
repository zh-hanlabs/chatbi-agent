"""共享数据模型。

单独成模块以避免循环依赖：`primitives` 与 `gates` 都要用 Finding，
而 `gates` 又要调用 `primitives` 执行 DSL 规则。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SEVERITIES = ("error", "warn", "info")

SEVERITY_LABEL = {"error": "ERROR", "warn": "WARN", "info": "INFO"}


@dataclass
class Finding:
    rule: str
    message: str
    location: str = ""
    hint: str = ""
    severity: Optional[str] = None   # None 表示沿用规则自身级别

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "message": self.message,
            "location": self.location,
            "hint": self.hint,
            "severity": self.severity,
        }


@dataclass
class Rule:
    id: str
    title: str
    category: str
    severity: str
    hint: str = ""
    source: str = "builtin"          # builtin | dsl | project


@dataclass
class GateResult:
    phase: str
    scope: str
    mode: str
    findings: List[Finding] = field(default_factory=list)
    rules_run: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warns(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "warn"]

    @property
    def infos(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "info"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "scope": self.scope,
            "mode": self.mode,
            "ok": self.ok,
            "errors": len(self.errors),
            "warnings": len(self.warns),
            "infos": len(self.infos),
            "rules": len(self.rules_run),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary(),
            "rules_run": self.rules_run,
            "skipped": self.skipped,
            "findings": [dict(f.as_dict(), severity=f.severity) for f in self.findings],
        }
