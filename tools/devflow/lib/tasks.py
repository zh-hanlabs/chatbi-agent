"""任务（WBS）与排期管理。

任务存在 `state.json` 的 tasks 里，字段：
    id / title / phase / owner / estimate_h / priority / tags /
    status / start / due / depends_on / req / notes / updated_at / blocking
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .state import TASK_STATUS, now, today

VALID_STATUS = TASK_STATUS


def create_record(
    state, title: str, owner: str = "", phase: str = "", estimate_h: float = 0.0,
    priority: str = "P1", tags: Optional[List[str]] = None, due: str = "", start: str = "",
    depends_on: Optional[List[str]] = None, req: str = "", note: str = "", blocking: bool = False,
) -> Dict[str, Any]:
    task = {
        "id": state.next_task_id(),
        "title": title,
        "phase": phase or state.current_phase(),
        "owner": owner,
        "estimate_h": float(estimate_h or 0),
        "priority": priority,
        "tags": list(tags or []),
        "status": "todo",
        "start": start or today(),
        "due": due,
        "depends_on": list(depends_on or []),
        "req": req,
        "note": note,
        "blocking": bool(blocking),
        "created_at": now(),
        "updated_at": now(),
    }
    return task


def add(state, **kwargs: Any) -> Dict[str, Any]:
    task = create_record(state, **kwargs)
    state.add_task(task)
    return task


def update(state, task_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    task = state.find_task(task_id)
    if task is None:
        return None
    if "status" in fields and fields["status"] not in VALID_STATUS:
        raise ValueError("非法任务状态：%s（可选 %s）" % (fields["status"], "/".join(VALID_STATUS)))
    for key, value in fields.items():
        if key == "tags" and isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        if key == "depends_on" and isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        task[key] = value
    task["updated_at"] = now()
    return task


def _parse_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def stats(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    today_dt = _parse_date(today()) or datetime.now()
    done = [t for t in tasks if t.get("status") == "done"]
    total_est = sum(float(t.get("estimate_h") or 0) for t in tasks)
    done_est = sum(float(t.get("estimate_h") or 0) for t in done)
    overdue = []
    for task in tasks:
        if task.get("status") in ("done", "cancelled"):
            continue
        due_dt = _parse_date(str(task.get("due") or ""))
        if due_dt and due_dt < today_dt:
            overdue.append(task)
    return {
        "total": len(tasks),
        "done": len(done),
        "doing": len([t for t in tasks if t.get("status") == "doing"]),
        "blocked": len([t for t in tasks if t.get("status") == "blocked"]),
        "todo": len([t for t in tasks if t.get("status") == "todo"]),
        "estimate_h": round(total_est, 1),
        "done_estimate_h": round(done_est, 1),
        "percent": round(done_est / total_est * 100, 1) if total_est else 0.0,
        "overdue": overdue,
    }


def render_table(tasks: List[Dict[str, Any]], title: str = "任务清单") -> str:
    if not tasks:
        return "（暂无任务）"
    today_str = today()
    lines = [
        "| ID | 状态 | 标题 | 负责人 | 估时(h) | 截止 | 标签 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    icon = {"todo": "待办", "doing": "进行中", "blocked": "阻塞", "done": "完成", "cancelled": "取消"}
    for task in tasks:
        due = str(task.get("due") or "-")
        flag = ""
        if due != "-" and due < today_str and task.get("status") not in ("done", "cancelled"):
            flag = " ⚠逾期"
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            task.get("id"),
            icon.get(task.get("status"), task.get("status")),
            task.get("title"),
            task.get("owner") or "-",
            task.get("estimate_h") or "-",
            due + flag,
            ",".join(task.get("tags") or []) or "-",
        ))
    return "\n".join(lines)


def filter_tasks(tasks: List[Dict[str, Any]], **criteria: Any) -> List[Dict[str, Any]]:
    result = []
    for task in tasks:
        ok = True
        for key, value in criteria.items():
            if value is None or value == "":
                continue
            actual = task.get(key)
            if isinstance(value, list):
                if actual != value:
                    ok = False
            elif str(actual) != str(value):
                ok = False
        if ok:
            result.append(task)
    return result


def unplanned(tasks: List[Dict[str, Any]]) -> List[str]:
    """返回缺失关键排期字段的原因描述。"""
    issues = []
    for task in tasks:
        miss = []
        if not task.get("owner"):
            miss.append("owner")
        if not task.get("estimate_h"):
            miss.append("estimate_h")
        if not task.get("due"):
            miss.append("due")
        if miss:
            issues.append("%s(%s) 缺少 %s" % (task.get("id"), task.get("title"), "/".join(miss)))
    return issues


def blocking_open(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [t for t in tasks if t.get("blocking") and t.get("status") not in ("done", "cancelled")]
