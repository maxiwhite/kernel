"""Local-first, lease-protected task coordination for KERNEL."""

import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from .kernel import event, load, save, ready_tasks
except ImportError:
    from kernel import event, load, save, ready_tasks


class Coordinator:
    def __init__(self, board_root: Path, workers: int = 1, lease_seconds: int = 300):
        self.board_root = Path(board_root)
        self.workers = max(1, int(workers))
        self.lease_seconds = max(1, int(lease_seconds))
        self.lease_dir = self.board_root / "leases"
        self.cache_dir = self.board_root / "cache"

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
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing.get("expires", 0) <= time.time():
                    path.unlink()
                    event(self.board_root, "task.lease_expired", {"task_id": task_id})
            except (OSError, json.JSONDecodeError):
                return False
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

    def execute(self, task, argv, *, allowed_executables, timeout_seconds=300, cwd=None, cancel_event=None):
        """Run one explicitly allowlisted argv without invoking a shell."""
        started = time.monotonic()
        command = [str(part) for part in argv]
        cache_key = hashlib.sha256(json.dumps({"argv": command, "cwd": str(cwd or "")}, sort_keys=True).encode()).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        executable = command[0] if command else ""
        if not command or executable not in {str(item) for item in allowed_executables}:
            result = {"task_id": task["id"], "status": "blocked", "returncode": None,
                      "stdout": "", "stderr": "command is not allowlisted", "duration_ms": 0}
            event(self.board_root, "task.blocked", result)
            return result
        if cache_path.exists():
            result = json.loads(cache_path.read_text(encoding="utf-8"))
            result = {**result, "task_id": task["id"], "status": "cached", "duration_ms": 0}
            event(self.board_root, "task.cached", result)
            return result
        if cancel_event is not None and cancel_event.is_set():
            result = {"task_id": task["id"], "status": "cancelled", "returncode": None,
                      "stdout": "", "stderr": "cancelled before start", "duration_ms": 0}
            event(self.board_root, "task.cancelled", result)
            return result
        try:
            completed = subprocess.Popen(command, cwd=cwd, shell=False, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True)
            deadline = time.monotonic() + max(1, int(timeout_seconds))
            while completed.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    completed.terminate()
                    stdout, stderr = completed.communicate(timeout=2)
                    result = {"task_id": task["id"], "status": "cancelled", "returncode": completed.returncode,
                              "stdout": stdout[-10000:], "stderr": stderr[-10000:],
                              "duration_ms": round((time.monotonic() - started) * 1000)}
                    event(self.board_root, "task.cancelled", result)
                    return result
                if time.monotonic() >= deadline:
                    completed.terminate()
                    stdout, stderr = completed.communicate(timeout=2)
                    result = {"task_id": task["id"], "status": "failed", "returncode": None,
                              "stdout": stdout[-10000:], "stderr": "timeout exceeded",
                              "duration_ms": round((time.monotonic() - started) * 1000)}
                    event(self.board_root, "task.failed", result)
                    return result
                time.sleep(0.01)
            stdout, stderr = completed.communicate()
            status = "passed" if completed.returncode == 0 else "failed"
            result = {"task_id": task["id"], "status": status, "returncode": completed.returncode,
                      "stdout": stdout[-10000:], "stderr": stderr[-10000:],
                      "duration_ms": round((time.monotonic() - started) * 1000)}
        except subprocess.TimeoutExpired as exc:
            result = {"task_id": task["id"], "status": "failed", "returncode": None,
                      "stdout": str(exc.stdout or "")[-10000:], "stderr": "timeout exceeded",
                      "duration_ms": round((time.monotonic() - started) * 1000)}
        event(self.board_root, f"task.{result['status']}", result)
        if result["status"] == "passed":
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(result), encoding="utf-8")
        return result

    def execute_batch(self, items, *, allowed_executables, timeout_seconds=300, cwd=None, cancel_event=None):
        """Execute independent tasks concurrently, bounded by the worker cap."""
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(self.execute, task, argv,
                                   allowed_executables=allowed_executables,
                                   timeout_seconds=timeout_seconds, cwd=cwd,
                                   cancel_event=cancel_event)
                       for task, argv in items]
            return [future.result() for future in futures]

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
