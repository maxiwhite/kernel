"""Local-first, lease-protected task coordination for KERNEL."""

import json
import os
import time
from pathlib import Path

try:
    from .kernel import event, load, save, ready_tasks
except ImportError:  # CLI execution from the scripts directory
    from kernel import event, load, save, ready_tasks


class Coordinator:
    def __init__(self, board_root: Path, workers: int = 1, lease_seconds: int = 300):
        self.board_root = Path(board_root)
        self.workers = max(1, int(workers))
        self.lease_seconds = max(1, int(lease_seconds))
        self.lease_dir = self.board_root / "leases"

    def ready_tasks(self):
        return ready_tasks(load(self.board_root))

    def provider_order(self, task):
        data = load(self.board_root)
        configured_free = [
            p["name"] for p in data.get("providers", [])
            if p.get("name") != "local" and p.get("free_or_paid", "free") == "free"
            and p.get("availability") in {"available", "configured"}
        ]
        paid = [
            p["name"] for p in data.get("providers", [])
            if p.get("free_or_paid") == "paid" and p.get("availability") in {"available", "configured"}
            and task.get("approved")
        ]
        return ["local", *configured_free, "freebuff", *paid]

    def claim(self, task_id):
        self.lease_dir.mkdir(parents=True, exist_ok=True)
        path = self.lease_dir / f"{task_id}.json"
        payload = {"pid": os.getpid(), "created": time.time(), "expires": time.time() + self.lease_seconds}
        try:
            handle = path.open("x", encoding="utf-8")
            with handle:
                json.dump(payload, handle)
            event(self.board_root, "task.claimed", {"task_id": task_id, "pid": os.getpid()})
            return True
        except FileExistsError:
            return False

    def release(self, task_id):
        path = self.lease_dir / f"{task_id}.json"
        if path.exists():
            path.unlink()
            event(self.board_root, "task.released", {"task_id": task_id, "pid": os.getpid()})

    def run_batch(self):
        data = load(self.board_root)
        selected = []
        skipped = []
        for task in self.ready_tasks():
            if len(selected) >= self.workers:
                skipped.append({"task_id": task["id"], "reason": "worker_limit"})
                continue
            if not self.claim(task["id"]):
                skipped.append({"task_id": task["id"], "reason": "lease_conflict"})
                continue
            task["status"] = "staged"
            task["provider_candidates"] = self.provider_order(task)
            selected.append(task["id"])
            event(self.board_root, "task.staged", {"task_id": task["id"], "providers": task["provider_candidates"]})
        save(self.board_root, data)
        return {"status": "staged", "selected": selected, "skipped": skipped, "worker_limit": self.workers}
