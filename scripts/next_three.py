"""Pure, dependency-aware next-three action suggestions for KERNEL and its clients.

This module ranks *proposals*. It never executes commands, approves purchases,
merges pull requests or crosses project boundaries.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VERSION = 1
READY = {"ready", "planned"}
CLOSED = {"verified", "published", "done"}


def _priority(task: dict[str, Any]) -> tuple[int, int, str]:
    """High impact/urgency and low effort win; IDs break ties predictably."""
    impact = int(task.get("impact", 3))
    urgency = int(task.get("urgency", 3))
    effort = int(task.get("effort", 3))
    if any(not 1 <= v <= 5 for v in (impact, urgency, effort)):
        raise ValueError("impact, urgency and effort must each be 1..5")
    return (-(impact * 5 + urgency * 3 - effort * 2), effort, task["id"])


def recommend(
    tasks: list[dict[str, Any]], *, completed: set[str] | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Return at most 3 ranked suggestions with explicit why and handoff prompts.

    Clickable clients can send ``prompt`` as a new user message. The receiving
    assistant must still validate tool permissions, freshness and risk.
    """
    if not isinstance(tasks, list):
        raise TypeError("tasks must be a list")
    if not 1 <= limit <= 3:
        raise ValueError("limit must be between 1 and 3")
    done = set(completed or set())
    done.update(str(t.get("id")) for t in tasks if t.get("status") in CLOSED)
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()

    for task in tasks:
        if not isinstance(task, dict):
            raise TypeError("each task must be an object")
        identifier = str(task.get("id", "")).strip()
        label = task.get("title")
        prompt = task.get("prompt")
        if (not identifier or not isinstance(label, str) or not label.strip()
                or not isinstance(prompt, str) or not prompt.strip()):
            raise ValueError("each task requires nonempty id, title and prompt")
        if identifier in seen:
            raise ValueError(f"duplicate action id: {identifier}")
        seen.add(identifier)
        reason = None
        if task.get("status") not in READY:
            reason = "not_ready"
        elif set(task.get("depends_on", [])) - done:
            reason = "dependencies_unmet"
        elif task.get("approval_required") and not task.get("approved"):
            reason = "approval_missing"
        elif task.get("risk") in {"high", "critical"} and not task.get("risk_reviewed"):
            reason = "risk_review_missing"
        if reason:
            skipped.append({"id": identifier, "reason": reason})
            continue
        accepted.append(task)

    accepted.sort(key=_priority)
    options = []
    for index, task in enumerate(accepted[:limit]):
        options.append({
            "id": task["id"],
            "label": task["title"].strip(),
            "prompt": task["prompt"].strip(),
            "project": str(task.get("project", "")),
            "recommended": index == 0,
            "reason": ("High impact, urgency and achievable effort" if index == 0
                       else "Ready and independently actionable"),
        })
    return {"version": VERSION, "actions": options, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank at most three next actions")
    parser.add_argument("--input", required=True, type=Path, help="JSON task array or object with tasks")
    parser.add_argument("--completed", action="append", default=[])
    args = parser.parse_args(argv)
    loaded = json.loads(args.input.read_text(encoding="utf-8"))
    tasks = loaded.get("tasks") if isinstance(loaded, dict) else loaded
    print(json.dumps(recommend(tasks, completed=set(args.completed)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
