#!/usr/bin/env python3
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

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
def event(root, kind, payload):
    with (root / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now(), "kind": kind, "payload": payload}, sort_keys=True) + "\n")
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
    rv = sub.add_parser("review"); rv.add_argument("--root", action="append", required=True)
    sub.add_parser("next"); r = sub.add_parser("run-safe"); r.add_argument("task_id"); r.add_argument("--provider", default="local")
    v = sub.add_parser("verify"); v.add_argument("task_id"); v.add_argument("--evidence", required=True)
    rec = sub.add_parser("record"); rec.add_argument("kind"); rec.add_argument("payload", nargs="?", default="{}")
    sub.add_parser("provider-health"); a = sub.add_parser("approve"); a.add_argument("task_id")
    args = ap.parse_args(argv); data = load(args.board)
    if args.command == "scan": print(json.dumps(scan(args.board, args.root), indent=2)); return 0
    if args.command == "review": print(json.dumps(review(args.board, args.root), indent=2)); return 0
    if args.command == "status": print(json.dumps({"projects": len(data["projects"]), "tasks": {s: sum(t.get("status") == s for t in data["tasks"]) for s in STATUSES}}, indent=2)); return 0
    if args.command == "next":
        tasks = ready_tasks(data); print(json.dumps({"task": tasks[0] if tasks else None}, indent=2)); return 0
    if args.command == "run-safe":
        task = next((t for t in data["tasks"] if t.get("id") == args.task_id), None)
        if not task: print("task not found", file=sys.stderr); return 1
        paid = args.provider not in {"local", "freebuff", "free"}
        if paid and not task.get("approved"):
            print("approval required before paid provider execution", file=sys.stderr); return 2
        task["status"] = "active"; task["provider"] = args.provider; save(args.board, data); event(args.board, "task.started", {"task_id": args.task_id, "provider": args.provider}); print(json.dumps({"task_id": args.task_id, "provider": args.provider, "status": "active", "changed_paths": [], "cost_estimate": task.get("max_spend", 0) if paid else 0, "approval_required": paid, "verification_required": task.get("verification_required", True), "evidence": [], "error": None}, indent=2)); return 0
    if args.command == "verify":
        task = next((t for t in data["tasks"] if t.get("id") == args.task_id), None)
        if not task: print("task not found", file=sys.stderr); return 1
        task["status"] = "verified"; task["evidence"] = [args.evidence]; save(args.board, data); event(args.board, "task.verified", {"task_id": args.task_id, "evidence": args.evidence}); print(json.dumps(task, indent=2)); return 0
    if args.command == "approve":
        task = next((t for t in data["tasks"] if t.get("id") == args.task_id), None)
        if not task: return 1
        task["approved"] = True; save(args.board, data); event(args.board, "task.approved", {"task_id": args.task_id}); print(json.dumps(task, indent=2)); return 0
    if args.command == "record": event(args.board, args.kind, json.loads(args.payload)); print(json.dumps({"recorded": True})); return 0
    if args.command == "provider-health": print(json.dumps({"providers": [{"name": "local", "free_or_paid": "free", "availability": "available"}, {"name": "freebuff", "free_or_paid": "free", "availability": "configured-only"}]})); return 0
    return 0
if __name__ == "__main__": sys.exit(main())
