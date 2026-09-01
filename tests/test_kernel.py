import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
CLI = ROOT / "scripts" / "kernel.py"


def run(*args, board):
    return subprocess.run(
        [sys.executable, str(CLI), "--board", str(board), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_scan_discovers_canonical_and_todo_files(tmp_path):
    project = tmp_path / "site"
    project.mkdir()
    (project / "ARCHITECTURE.md").write_text("# Canon", encoding="utf-8")
    (project / "README.md").write_text("TODO: add tests\n", encoding="utf-8")
    board = tmp_path / "board"
    result = run("scan", "--root", str(project), board=board)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["projects"][0]["canonical"][0].endswith("ARCHITECTURE.md")
    assert any("add tests" in task["title"] for task in data["tasks"])


def test_next_excludes_tasks_with_unmet_dependencies(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    (board / "board.json").write_text(json.dumps({
        "projects": [],
        "tasks": [
            {"id": "a", "title": "Blocked", "status": "ready", "depends_on": ["missing"]},
            {"id": "b", "title": "Ready", "status": "ready", "depends_on": []},
        ],
    }), encoding="utf-8")
    result = run("next", board=board)
    assert result.returncode == 0
    assert json.loads(result.stdout)["task"]["id"] == "b"


def test_paid_provider_requires_approval(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    (board / "board.json").write_text(json.dumps({
        "projects": [],
        "tasks": [{"id": "paid", "title": "Paid work", "status": "ready", "risk": "low", "max_spend": 1}],
    }), encoding="utf-8")
    result = run("run-safe", "paid", "--provider", "premium", board=board)
    assert result.returncode == 2
    assert "approval" in result.stderr.lower()


def test_approved_paid_provider_can_start_and_records_cost(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    (board / "board.json").write_text(json.dumps({
        "projects": [], "tasks": [{"id": "paid", "title": "Paid work", "status": "ready", "max_spend": 2}]
    }), encoding="utf-8")
    assert run("approve", "paid", board=board).returncode == 0
    result = run("run-safe", "paid", "--provider", "premium", board=board)
    assert result.returncode == 0
    assert json.loads(result.stdout)["approval_required"] is True


def test_verify_requires_evidence_and_writes_event(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    (board / "board.json").write_text(json.dumps({
        "projects": [],
        "tasks": [{"id": "t", "title": "Test", "status": "staged"}],
    }), encoding="utf-8")
    result = run("verify", "t", "--evidence", "tests passed", board=board)
    assert result.returncode == 0
    data = json.loads((board / "board.json").read_text(encoding="utf-8"))
    assert data["tasks"][0]["status"] == "verified"
    assert (board / "events.jsonl").read_text(encoding="utf-8").count("task.verified") == 1


def test_review_reports_engine_start_recommendations(tmp_path):
    project = tmp_path / "site"
    project.mkdir()
    (project / "ARCHITECTURE.md").write_text("# Canon", encoding="utf-8")
    board = tmp_path / "board"
    result = run("review", "--root", str(project), board=board)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["scope"]["roots_scanned"] == 1
    assert "Connect Freebuff" in report["recommendations"]
    assert report["next_safe_task"] is None


def test_run_ready_execute_requires_explicit_allowlist(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    (board / "board.json").write_text(json.dumps({
        "projects": [],
        "tasks": [{"id": "run", "status": "ready", "command": [sys.executable, "-c", "print('ok')"]}],
    }), encoding="utf-8")
    result = run("run-ready", "--execute", "--allowed-executable", sys.executable, board=board)
    assert result.returncode == 0
    assert json.loads(result.stdout)["executed"] == ["run"]


def test_run_ready_enforces_allowed_root(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (board / "board.json").write_text(json.dumps({
        "projects": [], "tasks": [{"id": "run", "status": "ready",
        "command": [sys.executable, "-c", "print('no')"], "cwd": str(outside)}],
    }), encoding="utf-8")
    result = run("run-ready", "--execute", "--allowed-executable", sys.executable,
                 "--allowed-root", str(board), board=board)
    assert json.loads(result.stdout)["failed"] == ["run"]


def test_metrics_reports_execution_and_verification_counts(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    (board / "board.json").write_text(json.dumps({
        "projects": [], "tasks": [{"id": "done", "status": "verified"}],
    }), encoding="utf-8")
    (board / "events.jsonl").write_text(
        '{"kind":"task.passed","payload":{"duration_ms":12}}\n'
        '{"kind":"task.cached","payload":{"duration_ms":0}}\n', encoding="utf-8"
    )
    result = run("metrics", board=board)
    report = json.loads(result.stdout)
    assert report["verified_tasks"] == 1
    assert report["passed_runs"] == 1
    assert report["cache_hits"] == 1


def test_provider_health_reads_repository_configuration(tmp_path):
    result = run("provider-health", board=tmp_path / "board")
    report = json.loads(result.stdout)
    assert any(provider["name"] == "local" for provider in report["providers"])


def test_register_persists_explicit_project_boundary(tmp_path):
    board = tmp_path / "board"
    project = tmp_path / "subangel"
    project.mkdir()
    result = run("register", "subangel", "--name", "SUBANGEL", "--root", str(project),
                 "--owner", "maxiwhite", "--authority", "local", board=board)
    assert result.returncode == 0
    registered = json.loads(result.stdout)["project"]
    assert registered["id"] == "subangel"
    assert registered["owner"] == "maxiwhite"
    assert registered["authority"] == "local"
    assert registered["data_root"] == str(project.resolve())


def test_register_rejects_identity_collision(tmp_path):
    board = tmp_path / "board"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    assert run("register", "oracle", "--name", "Oracle", "--root", str(first),
               "--owner", "maxiwhite", "--authority", "local", board=board).returncode == 0
    result = run("register", "oracle", "--name", "Oracle", "--root", str(second),
                 "--owner", "other", "--authority", "remote", board=board)
    assert result.returncode == 2
    assert "identity collision" in result.stderr.lower()

