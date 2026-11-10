"""Tests for the governed checks."""

from governed_agent.checks import (
    BudgetCheck,
    CitationRequired,
    EvidenceMatchesFile,
    NoSecretsInOutput,
    NoWriteWithoutApproval,
    default_checks,
)


def _draft_args(**over):
    args = {"file": "f.py", "line": 2, "evidence": "b = 2"}
    args.update(over)
    return {"tool": {"name": "draft_finding"}, "args": args}


def test_citation_required_passes_for_real_line(tmp_path):
    (tmp_path / "f.py").write_text("a = 1\nb = 2\n")
    assert CitationRequired(tmp_path).run(_draft_args()).passed


def test_citation_required_fails_for_missing_file(tmp_path):
    result = CitationRequired(tmp_path).run(_draft_args(file="nope.py"))
    assert not result.passed
    assert "does not exist" in result.reason


def test_citation_required_fails_for_line_out_of_range(tmp_path):
    (tmp_path / "f.py").write_text("a = 1\n")
    result = CitationRequired(tmp_path).run(_draft_args(line=999))
    assert not result.passed
    assert "out of range" in result.reason


def test_citation_required_is_retryable_not_fatal(tmp_path):
    check = CitationRequired(tmp_path)
    assert check.stops_run is False
    assert check.run(_draft_args(file="nope.py")).passed is False


def test_citation_required_ignores_other_tools(tmp_path):
    ctx = {"tool": {"name": "read_file"}, "args": {"path": "f.py"}}
    assert CitationRequired(tmp_path).run(ctx).passed


def test_evidence_matches_file_passes(tmp_path):
    (tmp_path / "f.py").write_text("def divide(a, b):\n    return a // b\n")
    ctx = _draft_args(line=2, evidence="return a // b")
    assert EvidenceMatchesFile(tmp_path).run(ctx).passed


def test_evidence_matches_file_fails_on_invented_evidence(tmp_path):
    (tmp_path / "f.py").write_text("def divide(a, b):\n    return a // b\n")
    ctx = _draft_args(line=2, evidence="def secret(): pass")
    result = EvidenceMatchesFile(tmp_path).run(ctx)
    assert not result.passed
    assert "hallucinated" in result.reason


def test_no_write_without_approval(tmp_path):
    check = NoWriteWithoutApproval()
    assert check.stops_run is True
    mutating = {"tool": {"name": "write_file", "mutates": True}, "args": {}, "approved": False}
    assert not check.run(mutating).passed
    approved = {"tool": {"name": "write_file", "mutates": True}, "args": {}, "approved": True}
    assert check.run(approved).passed
    read_only = {"tool": {"name": "read_file", "mutates": False}, "args": {}, "approved": False}
    assert check.run(read_only).passed


def test_no_secrets_in_output(tmp_path):
    check = NoSecretsInOutput()
    assert check.stops_run is True
    leaked = {"tool": {"name": "draft_finding"}, "args": {"evidence": "api_key = 'abcdefghijklmnop'"}}
    assert not check.run(leaked).passed
    clean = {"tool": {"name": "draft_finding"}, "args": {"evidence": "return a // b"}}
    assert check.run(clean).passed


def test_budget_check(tmp_path):
    check = BudgetCheck(max_steps=2, max_model_calls=3)
    assert check.run({"step": 2, "model_calls": 3}).passed
    result = check.run({"step": 3, "model_calls": 3})
    assert not result.passed
    assert "step budget" in result.reason
    result = check.run({"step": 1, "model_calls": 4})
    assert not result.passed
    assert "model-call budget" in result.reason


def test_default_checks_include_citation_evidence_and_budget(tmp_path):
    checks = default_checks(tmp_path, max_steps=8, max_model_calls=12)
    names = {c.name for c in checks}
    assert {
        "no_write_without_approval",
        "citation_required",
        "evidence_matches_file",
        "no_secrets_in_output",
        "budget",
    } <= names
