"""Tests for the evidence-first repo reviewer."""

import json
from pathlib import Path

from governed_agent.models import ScriptedModel
from governed_agent.reviewer import review_repo

ROOT = Path(__file__).resolve().parents[1]
DEMO_REPO = ROOT / "demo-repo"


def _j(obj):
    return json.dumps(obj)


DEMO_SCRIPT = [
    _j({"tool": "list_dir", "args": {"path": "."}}),
    _j({"tool": "read_file", "args": {"path": "calculator.py"}}),
    _j({"tool": "run_tests", "args": {"path": "."}}),
    _j({"tool": "read_file", "args": {"path": "test_calculator.py"}}),
    _j({"tool": "draft_finding", "args": {"title": "divide() uses integer division", "file": "calculator.py", "line": 24, "evidence": "return a // b", "confidence": "high", "severity": "high"}}),
    _j({"tool": "draft_finding", "args": {"title": "average() divides by len(values) + 1", "file": "calculator.py", "line": 31, "evidence": "return sum(values) / (len(values) + 1)", "confidence": "high", "severity": "high"}}),
    _j({"done": True, "result": "reviewed calculator.py; two defects demonstrated by failing tests"}),
]


def test_review_finds_both_injected_bugs(tmp_path):
    report = review_repo(DEMO_REPO, ScriptedModel(script=DEMO_SCRIPT), audit_dir=tmp_path / "audit")
    assert report.status == "finished"
    assert len(report.findings) == 2
    by_line = {f.line: f for f in report.findings}
    assert 24 in by_line and 31 in by_line
    assert by_line[24].title == "divide() uses integer division"
    assert by_line[24].confidence == "high"
    assert by_line[24].file == "calculator.py"
    assert by_line[31].title == "average() divides by len(values) + 1"
    # Every finding cites a real file/line and carries evidence.
    for f in report.findings:
        assert f.evidence
        assert (DEMO_REPO / f.file).exists()
        assert 1 <= f.line <= len((DEMO_REPO / f.file).read_text().splitlines())
    # Audit log and manifest written.
    assert report.audit_path.exists()
    assert report.manifest_path.exists()
    assert report.run_id


def test_review_rejects_fake_citation(tmp_path):
    script = [
        _j({"tool": "draft_finding", "args": {"title": "Hidden defect", "file": "calculator.py", "line": 999, "evidence": "def secret(): pass", "confidence": "medium", "severity": "high"}}),
        _j({"done": True, "result": "review complete"}),
    ]
    report = review_repo(DEMO_REPO, ScriptedModel(script=script), audit_dir=tmp_path / "audit")
    assert report.status == "finished"
    assert report.findings == []  # the fake citation never became a finding


def test_review_never_writes_or_sends(tmp_path):
    report = review_repo(DEMO_REPO, ScriptedModel(script=DEMO_SCRIPT), audit_dir=tmp_path / "audit")
    assert report.status == "finished"
    # The demo repo's source files are untouched. (Running its tests
    # creates pytest cache dirs — normal pytest behaviour, not a write
    # by the reviewer.)
    source_files = sorted(
        p.name for p in DEMO_REPO.iterdir() if p.name not in {".pytest_cache", "__pycache__"}
    )
    assert source_files == ["README.md", "calculator.py", "test_calculator.py"]
    assert "return a // b" in (DEMO_REPO / "calculator.py").read_text()


def test_report_serializes(tmp_path):
    report = review_repo(DEMO_REPO, ScriptedModel(script=DEMO_SCRIPT), audit_dir=tmp_path / "audit")
    data = json.loads(report.to_json())
    assert data["run_id"] == report.run_id
    assert len(data["findings"]) == 2
    assert "# Review:" in report.to_markdown()
    assert "Findings: 2" in report.to_markdown()
