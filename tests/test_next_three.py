import json
import subprocess
import sys

import pytest

from scripts.next_three import recommend


def item(id, impact=3, urgency=3, effort=3, **extra):
    return {"id": id, "title": f"Action {id}", "prompt": f"Work on task {id} and verify the outcome.",
            "status": "ready", "impact": impact, "urgency": urgency, "effort": effort, **extra}


def test_recommends_exactly_three_in_priority_order():
    report = recommend([item("a", 3), item("d", 1), item("c", 4), item("b", 5)])
    assert [a["id"] for a in report["actions"]] == ["b", "c", "a"]
    assert [a["recommended"] for a in report["actions"]] == [True, False, False]


def test_blocked_risky_draft_and_unapproved_actions_are_not_offered():
    tasks = [item("good"), item("draft", status="draft"),
             item("dep", depends_on=["missing"]),
             item("approval", approval_required=True),
             item("risky", risk="high"), item("blocked", status="blocked")]
    report = recommend(tasks)
    assert [a["id"] for a in report["actions"]] == ["good"]
    assert {s["reason"] for s in report["skipped"]} == {
        "not_ready", "dependencies_unmet", "approval_missing", "risk_review_missing"}


def test_completed_dependencies_unlock_action_without_claiming_execution():
    report = recommend([item("first", status="verified"),
                        item("second", depends_on=["first"])])
    assert [a["id"] for a in report["actions"]] == ["second"]
    assert "status" not in report["actions"][0]


def test_can_supply_verified_dependency_externally():
    assert recommend([item("b", depends_on=["a"])], completed={"a"})["actions"][0]["id"] == "b"


def test_never_returns_more_than_three_even_with_large_input():
    assert len(recommend([item(str(n)) for n in range(20)])[ "actions"]) == 3


def test_invalid_or_duplicate_actions_fail_closed():
    with pytest.raises(ValueError, match="duplicate"):
        recommend([item("a"), item("a")])
    with pytest.raises(ValueError, match="title"):
        recommend([{"id": "a", "title": "", "prompt": "Run"}])
    with pytest.raises(ValueError, match="1..5"):
        recommend([item("a", impact=7)])


def test_deterministic_on_equal_priority():
    report = recommend([item("z"), item("a")])
    assert [x["id"] for x in report["actions"]] == ["a", "z"]


def test_cli_reads_json_and_outputs_only_json(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"tasks": [item("one")]}), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "scripts.next_three", "--input", str(path)],
                          capture_output=True, text=True, check=True)
    assert json.loads(proc.stdout)["actions"][0]["id"] == "one"


def test_approved_reviewed_high_risk_action_can_be_suggested_but_not_executed():
    report = recommend([item("release", risk="high", risk_reviewed=True,
                             approval_required=True, approved=True)])
    assert report["actions"][0]["id"] == "release"
    assert "result" not in report["actions"][0]
