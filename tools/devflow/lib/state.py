"""状态机与进度持久化。

单一数据源：`{paths.state_dir}/state.json`
事件日志（append-only）：`{paths.state_dir}/log.jsonl`
人类可读快照：`{paths.state_dir}/STATUS.md`

所有写操作均为「写临时文件 + os.replace」的原子替换，避免中断导致状态损坏。
`state.json` 应当随代码提交到仓库，这样进度才能跨会话、跨机器持久化并可被评审。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

STATE_VERSION = "1.0"

PHASE_STATUS = ("pending", "active", "completed", "skipped", "blocked")
TASK_STATUS = ("todo", "doing", "blocked", "done", "cancelled")

PHASE_ICON = {
    "pending": "[ ]",
    "active": "[~]",
    "completed": "[x]",
    "skipped": "[-]",
    "blocked": "[!]",
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".devflow-", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _touch(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


class State:
    def __init__(self, root: str, data: Dict[str, Any], state_dir: str):
        self.root = root
        self.data = data
        self.state_dir = state_dir

    # ---------- 读写 ----------
    @classmethod
    def load(cls, root: str, state_dir: str) -> Optional["State"]:
        path = os.path.join(root, state_dir, "state.json")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(root, data, state_dir)

    @classmethod
    def create(cls, root: str, state_dir: str, project: Dict[str, Any], phases: List[str]) -> "State":
        data = {
            "version": STATE_VERSION,
            "project": project,
            "created_at": now(),
            "updated_at": now(),
            "current_phase": phases[0] if phases else "",
            "phases": {
                pid: {
                    "status": "active" if i == 0 else "pending",
                    "entered_at": now() if i == 0 else None,
                    "exited_at": None,
                    "attempts": 0,
                    "last_check": None,
                }
                for i, pid in enumerate(phases)
            },
            "artifacts": [],
            "tasks": [],
            "approvals": [],
            "history": [],
            "counters": {},
        }
        return cls(root, data, state_dir)

    def save(self) -> None:
        self.data["updated_at"] = now()
        path = os.path.join(self.root, self.state_dir, "state.json")
        _atomic_write(path, json.dumps(self.data, ensure_ascii=False, indent=2) + "\n")

    def log(self, event: str, **payload: Any) -> None:
        """追加事件到 log.jsonl（append-only，不做复写）。"""
        _touch(os.path.join(self.root, self.state_dir, "log.jsonl"))
        path = os.path.join(self.root, self.state_dir, "log.jsonl")
        record = {"ts": now(), "event": event}
        record.update(payload)
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        path = os.path.join(self.root, self.state_dir, "log.jsonl")
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8") as fh:
            lines = [line for line in fh.read().splitlines() if line.strip()]
        records: List[Dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:  # pragma: no cover
                continue
        return records

    # ---------- 阶段 ----------
    def phases(self) -> Dict[str, Dict[str, Any]]:
        return self.data.setdefault("phases", {})

    def phase_status(self, pid: str) -> str:
        return self.phases().get(pid, {}).get("status", "pending")

    def current_phase(self) -> str:
        return self.data.get("current_phase", "")

    def set_phase_status(self, pid: str, status: str, note: str = "") -> None:
        if status not in PHASE_STATUS:
            raise ValueError("非法阶段状态：%s" % status)
        entry = self.phases().setdefault(pid, {"status": "pending"})
        entry["status"] = status
        if status == "active":
            entry["entered_at"] = now()
            if note:
                entry["note"] = note
        elif status == "completed":
            entry["exited_at"] = now()

    def set_current_phase(self, pid: str) -> None:
        self.data["current_phase"] = pid

    def completed_phases(self) -> List[str]:
        return [pid for pid, info in self.phases().items() if info.get("status") == "completed"]

    def mark_checked(self, pid: str, ok: bool, errors: int, warns: int) -> None:
        entry = self.phases().setdefault(pid, {"status": "pending"})
        entry["last_check"] = {
            "at": now(),
            "ok": bool(ok),
            "errors": errors,
            "warnings": warns,
        }

    # ---------- 文档 ----------
    def artifacts(self) -> List[Dict[str, Any]]:
        return self.data.setdefault("artifacts", [])

    def add_artifact(self, kind: str, art_id: str, title: str, rel: str, phase: str) -> Dict[str, Any]:
        record = {
            "id": art_id,
            "kind": kind,
            "phase": phase,
            "title": title,
            "path": rel,
            "created_at": now(),
            "updated_at": now(),
        }
        self.artifacts().append(record)
        return record

    def find_artifact(self, art_id: str) -> Optional[Dict[str, Any]]:
        for item in self.artifacts():
            if item.get("id", "").lower() == art_id.lower():
                return item
        return None

    def remove_artifact(self, art_id: str) -> bool:
        before = len(self.artifacts())
        self.data["artifacts"] = [a for a in self.artifacts() if a.get("id", "").lower() != art_id.lower()]
        return len(self.artifacts()) != before

    def sync_artifact(self, art_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        art = self.find_artifact(art_id)
        if art is None:
            return None
        art.update(fields)
        art["updated_at"] = now()
        return art

    # ---------- 任务 ----------
    def tasks(self) -> List[Dict[str, Any]]:
        return self.data.setdefault("tasks", [])

    def next_task_id(self) -> str:
        seq = self.data.setdefault("counters", {}).get("task", 0) + 1
        max_exist = 0
        for task in self.tasks():
            tid = str(task.get("id", ""))
            if tid.startswith("T-") and tid[2:].isdigit():
                max_exist = max(max_exist, int(tid[2:]))
        seq = max(seq, max_exist + 1)
        self.data["counters"]["task"] = seq
        return "T-%03d" % seq

    def find_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        for task in self.tasks():
            if task.get("id", "").lower() == task_id.lower():
                return task
        return None

    def add_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.tasks().append(task)
        return task

    # ---------- 评审 ----------
    def approvals(self) -> List[Dict[str, Any]]:
        return self.data.setdefault("approvals", [])

    def add_approval(self, target: str, by: str, role: str, phase: str, decision: str = "approved") -> Dict[str, Any]:
        record = {
            "target": target,
            "by": by,
            "role": role,
            "phase": phase,
            "decision": decision,
            "at": now(),
        }
        self.approvals().append(record)
        return record

    def approvals_for(self, target: str) -> List[Dict[str, Any]]:
        return [a for a in self.approvals() if a.get("target", "").lower() == target.lower()]

    # ---------- 流转历史 ----------
    def push_history(self, record: Dict[str, Any]) -> None:
        self.data.setdefault("history", []).append(record)

    def last_gate(self) -> Optional[Dict[str, Any]]:
        return self.data.get("last_gate")

    def set_last_gate(self, result: Dict[str, Any]) -> None:
        self.data["last_gate"] = result
