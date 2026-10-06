"""Canonical workload assessment for KERNEL.

This layer does not execute work. It reduces concurrent work into one bounded
operator view, identifies dependency waits and duplicate candidates, and
records measurable context-cost fields when producers provide them.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any


ACTIVE_STATUSES = {"active", "staged"}
DONE_STATUSES = {"verified", "published"}
WAITING_STATUSES = {"planned", "ready"}
BLOCKED_STATUSES = {"blocked", "failed", "rejected"}


def _normalise_title(title: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(title).lower())
    return re.sub(r"\s+", " ", text).strip()


def _fingerprint(task: dict[str, Any]) -> str:
    project = str(task.get("project", ""))
    title = _normalise_title(task.get("title", task.get("id", "")))
    return hashlib.sha256(f"{project}|{title}".encode("utf-8")).hexdigest()[:16]


def assess(tasks: list[dict[str, Any]], *, now_limit: int = 1, next_limit: int = 3) -> dict[str, Any]:
    """Return a bounded operator assessment without changing task state.

    Priority is deliberately deterministic:
    1. active work already consuming execution capacity;
    2. ready work with no unmet dependencies;
    3. blocked/failed/rejected work;
    4. dependency-waiting work;
    5. planned low-risk work is parked rather than promoted.
    """

    by_id = {str(task.get("id")): task for task in tasks}
    duplicate_groups: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        duplicate_groups[_fingerprint(task)].append(str(task.get("id")))

    duplicates = [
        {"fingerprint": key, "task_ids": ids}
        for key, ids in duplicate_groups.items()
        if len(ids) > 1
    ]

    now: list[dict[str, Any]] = []
    next_items: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    parked: list[dict[str, Any]] = []

    for task in tasks:
        status = task.get("status", "planned")
        dependencies = [str(dep) for dep in task.get("depends_on", [])]
        unmet = [dep for dep in dependencies if by_id.get(dep, {}).get("status") not in DONE_STATUSES]

        item = {
            "task_id": task.get("id"),
            "project": task.get("project"),
            "title": task.get("title", task.get("id")),
            "status": status,
            "unmet_dependencies": unmet,
            "risk": task.get("risk", "low"),
            "estimated_tokens": task.get("estimated_tokens"),
            "context_cost": task.get("context_cost"),
        }

        if status in ACTIVE_STATUSES:
            now.append(item)
        elif status in BLOCKED_STATUSES:
            blocked.append(item)
        elif status in WAITING_STATUSES and not unmet:
            next_items.append(item)
        elif status in WAITING_STATUSES:
            waiting.append(item)
        else:
            parked.append(item)

    now.sort(key=lambda x: str(x["task_id"]))
    next_items.sort(key=lambda x: (x["risk"] != "high", str(x["task_id"])))
    waiting.sort(key=lambda x: (len(x["unmet_dependencies"]), str(x["task_id"])))
    blocked.sort(key=lambda x: str(x["task_id"]))
    parked.sort(key=lambda x: str(x["task_id"]))

    # Only the bounded top slice is actionable. Everything else remains visible
    # as waiting/parked evidence rather than becoming another queue to micromanage.
    bounded_now = now[: max(1, now_limit)]
    bounded_next = next_items[: max(1, next_limit)]

    token_values = [
        task.get("estimated_tokens")
        for task in tasks
        if isinstance(task.get("estimated_tokens"), (int, float))
    ]
    context_values = [
        task.get("context_cost")
        for task in tasks
        if isinstance(task.get("context_cost"), (int, float))
    ]

    return {
        "now": bounded_now,
        "next": bounded_next,
        "waiting": waiting,
        "blocked": blocked,
        "parked": parked,
        "overflow": {
            "active": max(0, len(now) - len(bounded_now)),
            "ready": max(0, len(next_items) - len(bounded_next)),
        },
        "duplicates": duplicates,
        "measurement": {
            "tasks": len(tasks),
            "estimated_tokens_total": sum(token_values) if token_values else None,
            "context_cost_total": sum(context_values) if context_values else None,
            "measured_task_count": len(token_values),
        },
    }
