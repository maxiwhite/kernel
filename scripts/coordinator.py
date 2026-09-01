"""Local-first, lease-protected task coordination for KERNEL."""

import json
import hashlib
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
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

    def select_provider(self, task, providers):
        """Select the first available adapter matching the task capability."""
        capability = task.get("capability")
        for name in self.provider_order(task):
            for provider in providers:
                if (provider.name == name and provider.availability in {"available", "configured"}
                        and (not capability or capability in provider.capabilities)
                        and (provider.free_or_paid != "paid" or task.get("approved"))):
                    return provider
        return None

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

    @staticmethod
    def _terminate_process_tree(process):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, check=False)
        else:
            process.terminate()

    def execute(self, task, argv, *, allowed_executables, timeout_seconds=300, cwd=None,
                cancel_event=None, allowed_roots=None):
        """Run one explicitly allowlisted argv without invoking a shell."""
        started = time.monotonic()
        command = [str(part) for part in argv]
        cache_key = hashlib.sha256(json.dumps({"argv": command, "cwd": str(cwd or "")}, sort_keys=True).encode()).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        executable = command[0] if command else ""
        if cwd is not None and allowed_roots:
            cwd_path = Path(cwd).resolve()
            roots = [Path(root).resolve() for root in allowed_roots]
            if not any(cwd_path == root or root in cwd_path.parents for root in roots):
                result = {"task_id": task["id"], "status": "blocked", "returncode": None,
                          "stdout": "", "stderr": "working directory is not allowlisted", "duration_ms": 0}
                event(self.board_root, "task.blocked", result)
                return result
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
            options = {"start_new_session": True} if os.name != "nt" else {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
            }
            completed = subprocess.Popen(command, cwd=cwd, shell=False, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True, **options)
            deadline = time.monotonic() + max(1, int(timeout_seconds))
            while completed.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    self._terminate_process_tree(completed)
                    stdout, stderr = completed.communicate(timeout=2)
                    result = {"task_id": task["id"], "status": "cancelled", "returncode": completed.returncode,
                              "stdout": stdout[-10000:], "stderr": stderr[-10000:],
                              "duration_ms": round((time.monotonic() - started) * 1000)}
                    event(self.board_root, "task.cancelled", result)
                    return result
                if time.monotonic() >= deadline:
                    self._terminate_process_tree(completed)
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

    def execute_batch(self, items, *, allowed_executables, timeout_seconds=300, cwd=None):
        """Execute independent tasks concurrently, bounded by the worker cap."""
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(self.execute, task, argv,
                                   allowed_executables=allowed_executables,
                                   timeout_seconds=timeout_seconds, cwd=cwd)
                       for task, argv in items]
            return [future.result() for future in futures]

    def run_provider(self, provider_name, task, provider, *, retries=0):
        """Run a provider adapter with bounded retries for failed results."""
        attempts = 0
        while True:
            attempts += 1
            result = dict(provider(task))
            if result.get("status") != "failed" or attempts > retries:
                result["provider"] = provider_name
                result["attempts"] = attempts
                event(self.board_root, f"provider.{result.get('status', 'unknown')}", result)
                return result

    def execute_with_provider(self, task, providers, *, retries=0):
        """Select and execute a capable provider adapter with bounded retries."""
        provider = self.select_provider(task, providers)
        if provider is None:
            result = {"task_id": task.get("id"), "status": "unavailable",
                      "error": "no available provider matches task capability"}
            event(self.board_root, "provider.unavailable", result)
            return result
        return self.run_provider(provider.name, task, provider.execute, retries=retries)

    def benchmark(self, tasks, argv, *, allowed_executables, repetitions=3, timeout_seconds=300, cwd=None):
        """Measure repeated execution, including cache reuse."""
        samples = []
        cache_hits = 0
        for index in range(max(1, int(repetitions))):
            result = self.execute(tasks[index % len(tasks)], argv,
                                  allowed_executables=allowed_executables,
                                  timeout_seconds=timeout_seconds, cwd=cwd)
            samples.append(result.get("duration_ms", 0))
            cache_hits += result.get("status") == "cached"
        report = {"runs": len(samples), "cache_hits": cache_hits,
                  "average_duration_ms": round(sum(samples) / len(samples), 2),
                  "min_duration_ms": min(samples), "max_duration_ms": max(samples)}
        event(self.board_root, "benchmark.completed", report)
        return report

    def run_ready(self, *, allowed_executables, timeout_seconds=300, cancel_event=None):
        """Execute ready tasks with explicit commands; stage the rest."""
        data = load(self.board_root)
        executed, staged, failed = [], [], []
        ready_ids = {task["id"] for task in self.ready_tasks()}
        for task in [task for task in data.get("tasks", []) if task.get("id") in ready_ids]:
            task_id = task["id"]
            if not task.get("command"):
                task["status"] = "staged"
                staged.append(task_id)
                event(self.board_root, "task.staged", {"task_id": task_id, "reason": "no command"})
                continue
            if not self.claim(task_id):
                failed.append(task_id)
                continue
            try:
                task["status"] = "active"
                result = self.execute(task, task["command"], allowed_executables=allowed_executables,
                                      timeout_seconds=timeout_seconds, cwd=task.get("cwd"), cancel_event=cancel_event)
                task["result"] = result
                task["status"] = "verified" if result["status"] in {"passed", "cached"} else result["status"]
                (executed if task["status"] == "verified" else failed).append(task_id)
            finally:
                self.release(task_id)
        save(self.board_root, data)
        return {"executed": executed, "staged": staged, "failed": failed}

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

