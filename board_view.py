#!/usr/bin/env python3
import argparse, html, json
from pathlib import Path

def main():
    ap = argparse.ArgumentParser(description="Render a readable KERNEL board")
    ap.add_argument("--board", type=Path, default=Path(".kernel"))
    ap.add_argument("--output", type=Path, default=Path("KERNEL Board.html"))
    args = ap.parse_args()
    data = json.loads((args.board / "board.json").read_text(encoding="utf-8")) if (args.board / "board.json").exists() else {"projects": [], "tasks": []}
    tasks = data.get("tasks", [])
    counts = {s: sum(t.get("status") == s for t in tasks) for s in ("active", "blocked", "staged", "verified", "planned")}
    next_task = next((t for t in tasks if t.get("status") in {"ready", "planned"}), None)
    def row(task):
        status = html.escape(task.get("status", "planned")); title = html.escape(task.get("title", "Untitled")); project = html.escape(task.get("project", "Unassigned")); risk = html.escape(task.get("risk", "low"))
        return f'<div class="task"><span class="pill {status}">{status}</span><div class="task-main"><strong>{title}</strong><span>{project}</span></div><span class="risk">{risk} risk</span></div>'
    cards = "".join(row(t) for t in tasks[:40]) or '<p class="empty">No tasks are registered yet. Run a KERNEL scan to begin.</p>'
    recommendation = html.escape(next_task["title"]) if next_task else "Run a catch-up review and register the first safe task."
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KERNEL Board</title><style>
    :root{{--ink:#172126;--muted:#657378;--line:#d6dfdc;--paper:#f4f6f2;--panel:#ffffff;--signal:#ae5d3d;--calm:#4a7d72}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:52px 28px}}header{{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid var(--line);padding-bottom:24px;margin-bottom:32px}}.eyebrow{{color:var(--signal);letter-spacing:.16em;text-transform:uppercase;font-size:11px;font-weight:700}}h1{{font:500 clamp(42px,8vw,78px)/.9 Georgia,serif;margin:10px 0 0}}.date,.task-main span,.risk{{color:var(--muted);font-size:13px}}.next{{background:var(--ink);color:#eef2ed;padding:24px 26px;margin-bottom:28px;box-shadow:10px 10px 0 #dbe2dc}}.next h2{{font:500 28px Georgia,serif;margin:8px 0}}.next p{{margin:0;color:#c9d6d0}}.stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:32px}}.stat{{background:var(--panel);padding:18px}}.stat strong{{display:block;font:500 30px Georgia,serif}}.stat span{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.1em}}section{{border-top:1px solid var(--line);padding-top:18px}}section h2{{font:500 25px Georgia,serif}}.tasks{{background:var(--panel);border-top:1px solid var(--line)}}.task{{display:flex;align-items:center;gap:18px;padding:15px 16px;border-bottom:1px solid var(--line);min-height:66px}}.task:hover{{background:#f0f4f0}}.task-main{{display:grid;gap:2px;flex:1;min-width:0}}.task-main strong{{font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.pill{{display:inline-block;min-width:78px;text-align:center;border-radius:999px;padding:4px 9px;font-size:10px;text-transform:uppercase;letter-spacing:.08em;background:#e4e9e5;color:var(--muted)}}.pill.active,.pill.staged{{background:#eee7d5;color:#8b5b25}}.pill.blocked,.pill.failed{{background:#f1dcd6;color:#99452f}}.pill.verified,.pill.published{{background:#dcece6;color:var(--calm)}}.empty{{color:var(--muted);padding:20px}}@media(max-width:650px){{main{{padding:28px 18px}}header{{display:block}}.date{{margin-top:14px}}.stats{{grid-template-columns:repeat(2,1fr)}}.task{{align-items:flex-start;gap:10px;flex-wrap:wrap}}.task-main{{flex-basis:calc(100% - 100px)}}.risk{{margin-left:88px}}}}
    </style></head><body><main><header><div><div class="eyebrow">Oracle work coordination</div><h1>KERNEL</h1></div><div class="date">Local board · readable view</div></header><div class="next"><div class="eyebrow">Next safe action</div><h2>{recommendation}</h2><p>Review the evidence, then decide whether to run it.</p></div><div class="stats">{''.join(f'<div class="stat"><strong>{counts[s]}</strong><span>{s}</span></div>' for s in counts)}</div><section><h2>Work on the board</h2><div class="tasks">{cards}</div></section></main></body></html>'''
    args.output.write_text(page, encoding="utf-8")
    print(args.output.resolve())
if __name__ == "__main__": main()
