"""Tests for the eval suite (task integrity, grading, pass@k)."""

import json
from pathlib import Path

import pytest

from governed_agent.evals import (
    build_fix_script,
    build_review_script,
    grade_review,
    load_tasks,
    pass_at_k,
)

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "evals" / "tasks.json"
FIXTURES = ROOT / "evals" / "fixtures"


def test_task_set_loads_and_hashes_verify():
    tasks = load_tasks(TASKS, FIXTURES)
    assert len(tasks) == 6
    assert {t["id"] for t in tasks} == {
        "fix-01", "fix-02", "fix-03", "review-01", "review-02", "review-03",
    }


def test_tampered_task_is_rejected(tmp_path):
    data = json.loads(TASKS.read_text())
    data["tasks"][0]["description"] = "tampered"
    bad = tmp_path / "tasks.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="hash mismatch"):
        load_tasks(bad, FIXTURES)


def test_pass_at_k_values():
    assert pass_at_k(3, 0, 1) == 0.0
    assert pass_at_k(3, 3, 1) == 1.0
    assert pass_at_k(3, 3, 3) == 1.0
    assert pass_at_k(3, 1, 1) == pytest.approx(1 / 3)
    # 1 pass in 3: 2 of the 3 possible 2-samples contain the pass.
    assert pass_at_k(3, 1, 2) == pytest.approx(2 / 3)
    # 2 passes in 3: every 2-sample contains a pass.
    assert pass_at_k(3, 2, 2) == 1.0


def test_grade_review_precision_and_recall():
    known = [{"file": "target.py", "line": 6}, {"file": "target.py", "line": 11}]
    findings = [
        {"file": "target.py", "line": 6},
        {"file": "target.py", "line": 11},
    ]
    g = grade_review(findings, known)
    assert g["precision"] == 1.0 and g["recall"] == 1.0
    g = grade_review(findings + [{"file": "target.py", "line": 1}], known)
    assert g["precision"] == pytest.approx(2 / 3)
    assert g["recall"] == 1.0
    g = grade_review([{"file": "target.py", "line": 1}], known)
    assert g["precision"] == 0.0 and g["recall"] == 0.0
    # Clean fixture: no known bugs, no findings.
    g = grade_review([], [])
    assert g["precision"] is None and g["recall"] is None


def test_fix_scripts_by_seed():
    tasks = {t["id"]: t for t in load_tasks(TASKS, FIXTURES)}
    seed0 = build_fix_script(tasks["fix-01"], 0)
    seed1 = build_fix_script(tasks["fix-01"], 1)
    seed2 = build_fix_script(tasks["fix-01"], 2)
    assert any("write_file" in s for s in seed0)
    assert any("write_file" in s for s in seed1)
    assert not any("write_file" in s for s in seed2)
    assert seed0 != seed1  # correct fix vs wrong fix differ


def test_review_scripts_by_seed():
    tasks = {t["id"]: t for t in load_tasks(TASKS, FIXTURES)}
    fixture = FIXTURES / "review-02"
    seed0 = build_review_script(tasks["review-02"], 0, fixture)
    seed1 = build_review_script(tasks["review-02"], 1, fixture)
    seed2 = build_review_script(tasks["review-02"], 2, fixture)
    assert len([s for s in seed0 if "draft_finding" in s]) == 2
    assert len([s for s in seed1 if "draft_finding" in s]) == 3  # +1 false positive
    assert len([s for s in seed2 if "draft_finding" in s]) == 1
    assert '"line": 999' in seed2[2]
