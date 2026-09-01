import json
from pathlib import Path

from scripts.coordinator import Coordinator


def write_board(root: Path, tasks: list[dict], providers: list[dict] | None = None):
    root.mkdir(exist_ok=True)
    (root / "board.json").write_text(json.dumps({
        "version": 1,
        "projects": [],
        "tasks": tasks,
        "providers": providers or [],
        "policy": {"paid_requires_approval": True},
    }), encoding="utf-8")


def test_ready_tasks_exclude_unmet_dependencies_and_active_tasks(tmp_path):
    write_board(tmp_path, [
        {"id": "blocked", "status": "planned", "depends_on": ["missing"]},
        {"id": "active", "status": "active", "depends_on": []},
        {"id": "ready", "status": "planned", "depends_on": []},
    ])
    assert [task["id"] for task in Coordinator(tmp_path).ready_tasks()] == ["ready"]


def test_provider_order_prefers_local_then_configured_free_then_approved_paid(tmp_path):
    write_board(tmp_path, [], providers=[
        {"name": "paid", "free_or_paid": "paid", "availability": "available"},
        {"name": "free", "free_or_paid": "free", "availability": "available"},
    ])
    task = {"id": "t", "status": "planned", "approved": True}
    assert Coordinator(tmp_path).provider_order(task) == ["local", "free", "freebuff", "paid"]


def test_claim_creates_lease_and_second_coordinator_cannot_claim(tmp_path):
    write_board(tmp_path, [{"id": "ready", "status": "planned", "depends_on": []}])
    first = Coordinator(tmp_path)
    second = Coordinator(tmp_path)
    assert first.claim("ready") is True
    assert second.claim("ready") is False
    first.release("ready")


def test_run_batch_respects_worker_limit_and_stages_tasks_without_executor(tmp_path):
    write_board(tmp_path, [
        {"id": "a", "status": "planned", "depends_on": []},
        {"id": "b", "status": "planned", "depends_on": []},
    ])
    result = Coordinator(tmp_path, workers=1).run_batch()
    assert result["selected"] == ["a"]
    assert result["worker_limit"] == 1
    assert result["status"] == "staged"
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    assert events.count('"kind": "task.staged"') == 1

