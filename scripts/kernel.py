#!/usr/bin/env python3
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATUSES = {"planned", "ready", "active", "staged", "verified", "blocked", "rejected", "failed", "published"}

def now(): return datetime.now(timezone.utc).isoformat()
def board_file(root): return root / "board.json"
def load(root):
    root.mkdir(parents=True, exist_ok=True)
    p = board_file(root)
    if not p.exists():
        data = {"version": 1, "projects": [], "tasks": [], "providers": [], "policy": {"paid_requires_approval": True}}
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data
    return json.loads(p.read_text(encoding="utf-8"))
def save(root, data): board_file(root).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
def register_project(root, project_id, name, project_root, owner, authority):
    data = load(root)
    normalized = {"id": project_id, "name": name, "path": str(Path(project_root).resolve()),
                  "owner": owner, "authority": authority, "data_root": str(Path(project_root).resolve()),
                  "canonical": []}
    existing = next((p for p in data["projects"] if p.get("id") == project_id), None)
    if existing and any(existing.get(key) != normalized[key] for key in ("name", "path", "owner", "authority", "data_root")):
        raise ValueError(f"identity collision for project {project_id}")
    if not existing:
        data["projects"].append(normalized)
        save(root, data)
        event(root, "project.registered", normalized)
        return normalized
    return existing
def event(root, kind, payload):
    with (root / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now(), "kind": kind, "payload": payload}, sort_keys=True) + "\n")
def metrics(root):
    data = load(root); counts = {s: sum(t.get("status") == s for t in data["tasks"]) for s in STATUSES}
    durations = []; passed = cached = failed = cancelled = 0
    journal = root / "events.jsonl"
    if journal.exists():
        for line in journal.read_text(encoding="utf-8", errors="ignore").splitlines():
            try: record = json.loads(line); kind = record.get("kind", ""); payload = record.get("payload", {})
            except json.JSONDecodeError: continue
            if kind == "task.passed": passed += 1
            if kind == "task.cached": cached += 1
            if kind == "task.failed": failed += 1
            if kind == "task.cancelled": cancelled += 1
            if isinstance(payload.get("duration_ms"), (int, float)): durations.append(payload["duration_ms"])
    return {"task_statuses": counts, "verified_tasks": counts.get("verified", 0), "passed_runs": passed,
            "cache_hits": cached, "failed_runs": failed, "cancelled_runs": cancelled,
            "average_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "measured_runs": len(durations)}
def scan(root, scan_root):
    data = load(root); path = Path(scan_root).resolve()
    project = next((p for p in data["projects"] if p.get("path") == str(path)), None)
    if not project:
        project = {"id": path.name.lower().replace(" ", "-"), "name": path.name, "path": str(path), "canonical": []}
        data["projects"].append(project)
    excluded = {"node_modules", ".git", "dist", "build", ".next", ".venv", "venv", "__pycache__"}
    inside = lambda p: not any(part in excluded for part in p.relative_to(path).parts)
    files = (p for p in path.rglob("*") if p.is_file() and inside(p))
    canonical = {str(p.resolve()) for p in files if re.search(r"(architecture|canonical|design|plan).*\.(md|txt|json)$", p.name, re.I)}
    project["canonical"] = sorted(canonical)
    for p in (p for p in path.rglob("*.md") if inside(p)):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                continue
            match = re.search(r"^\s*(?:[-*]\s*)?(?:TODO|NEXT|FIXME)\b\s*:?[ \t]*(.+)$", line, re.I)
            if not match:
                match = re.search(r"^\s*[-*]\s*\[ \]\s+(.+)$", line)
            if not match:
                continue
            title = match.group(1).strip()
            tid = re.sub(r"[^a-z0-9]+", "-", f"{path.name}-{title}".lower()).strip("-")[:80]
            if not any(t.get("id") == tid for t in data["tasks"]):
                data["tasks"].append({"id": tid, "title": title, "status": "planned", "project": project["id"], "canonical": project["canonical"][:1], "depends_on": [], "risk": "low", "max_spend": 0, "verification_required": True})
    save(root, data); event(root, "board.scanned", {"root": str(path)}); return data
def ready_tasks(data):
    done = {t["id"] for t in data["tasks"] if t.get("status") in {"verified", "published"}}
    return [t for t in data["tasks"] if t.get("status") in {"planned", "ready"} and all(d in done for d in t.get("depends_on", []))]
def review(root, roots):
    data = load(root)
    for scan_root in roots:
        data = scan(root, scan_root)
    statuses = {s: sum(t.get("status") == s for t in data["tasks"]) for s in STATUSES}
    recommendations = []
    if not data["projects"]:
        recommendations.append("Register the first project root")
    if not any(p.get("canonical") for p in data["projects"]):
        recommendations.append("Add or identify a canonical architecture document")
    if not any(t.get("status") in {"ready", "planned"} for t in data["tasks"]):
        recommendations.append("Create the first explicit ready task")
    recommendations.append("Connect Freebuff")
    recommendations.append("Run the next safe task and capture verification evidence")
    report = {"generated_at": now(), "scope": {"roots_scanned": len(roots), "projects": len(data["projects"])}, "status": statuses, "blockers": [t for t in data["tasks"] if t.get("status") in {"blocked", "failed"}], "next_safe_task": (ready_tasks(data) or [None])[0], "recommendations": recommendations}
    event(root, "board.reviewed", {"roots": roots, "recommendations": recommendations})
    return report
def main(argv=None):
    ap = argparse.ArgumentParser(prog="kernel")
    ap.add_argument("--board", type=Path, default=Path(".kernel"))
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("status"); s = sub.add_parser("scan"); s.add_argument("--root", required=True)
    reg = sub.add_parser("register"); reg.add_argument("project_id"); reg.add_argument("--name", required=True); reg.add_argument("--root", required=True); reg.add_argument("--owner", required=True); reg.add_argument("--authority", required=True)
    rv = sub.add_parser("review"); rv.add_argument("--root", action="append", required=True)
    sub.add_parser("next"); r = sub.add_parser("run-safe"); r.add_argument("task_id"); r.add_argument("--provider", default="local")
    rr = sub.add_parser("run-ready"); rr.add_argument("--workers", type=int, default=1); rr.add_argument("--execute", action="store_true"); rr.add_argument("--allowed-executable", action="append", default=[]); rr.add_argument("--allowed-root", action="append", default=[])
    v = sub.add_parser("verify"); v.add_argument("task_id"); v.add_argument("--evidence", required=True)
    rec = sub.add_parser("record"); rec.add_argument("kind"); rec.add_argument("payload", nargs="?", default="{}")
    sub.add_parser("provider-health"); sub.add_parser("metrics"); a = sub.add_parser("approve"); a.add_argument("task_id")
    args = ap.parse_args(argv); data = load(args.board)
    if args.command == "register":
        try:
            project = register_project(args.board, args.project_id, args.name, args.root, args.owner, args.authority)
        except ValueError as exc:
            print(str(exc), file=sys.stderr); return 2
        print(json.dumps({"project": project}, indent=2)); return 0
    if args.command == "scan": print(json.dumps(scan(args.board, args.root), indent=2)); return 0
    if args.command == "review": print(json.dumps(review(args.board, args.root), indent=2)); return 0
    if args.command == "status": print(json.dumps({"projects": len(data["projects"]), "tasks": {s: sum(t.get("status") == s for t in data["tasks"]) for s in STATUSES}}, indent=2)); return 0
    if args.command == "next":
        tasks = ready_tasks(data); print(json.dumps({"task": tasks[0] if tasks else None}, indent=2)); return 0
    if args.command == "run-ready":
        from coordinator import Coordinator
        coordinator = Coordinator(args.board, workers=args.workers)
        result = coordinator.run_ready(allowed_executables=args.allowed_executable, allowed_roots=args.allowed_root) if args.execute else coordinator.run_batch()
        print(json.dumps(result, indent=2)); return 0
    if args.command == "run-safe":
        task = next((t for t in data["tasks"] if t.get("id") == args.task_id), None)
        if not task: print("task not found", file=sys.stderr); return 1
        paid = args.provider not in {"local", "freebuff", "free"}
        if paid and not task.get("approved"):
            print("approval required before paid provider execution", file=sys.stderr); return 2
        task["status"] = "staged"; task["provider"] = args.provider; save(args.board, data); event(args.board, "task.staged", {"task_id": args.task_id, "provider": args.provider}); print(json.dumps({"task_id": args.task_id, "provider": args.provider, "status": "staged", "changed_paths": [], "cost_estimate": task.get("max_spend", 0) if paid else 0, "approval_required": paid, "verification_required": task.get("verification_required", True), "evidence": [], "error": None}, indent=2)); return 0
    if args.command == "verify":
        task = next((t for t in data["tasks"] if t.get("id") == args.task_id), None)
        if not task: print("task not found", file=sys.stderr); return 1
        task["status"] = "verified"; task["evidence"] = [args.evidence]; save(args.board, data); event(args.board, "task.verified", {"task_id": args.task_id, "evidence": args.evidence}); print(json.dumps(task, indent=2)); return 0
    if args.command == "approve":
        task = next((t for t in data["tasks"] if t.get("id") == args.task_id), None)
        if not task: return 1
        task["approved"] = True; save(args.board, data); event(args.board, "task.approved", {"task_id": args.task_id}); print(json.dumps(task, indent=2)); return 0
    if args.command == "record": event(args.board, args.kind, json.loads(args.payload)); print(json.dumps({"recorded": True})); return 0
    if args.command == "provider-health":
        from providers.adapter import load_adapters
        config = Path(__file__).parents[1] / "providers" / "providers.json"
        providers = [adapter.health() for adapter in load_adapters(config)] if config.exists() else []
        print(json.dumps({"providers": providers}, indent=2)); return 0
    if args.command == "metrics": print(json.dumps(metrics(args.board), indent=2)); return 0
    return 0
if __name__ == "__main__": sys.exit(main())

