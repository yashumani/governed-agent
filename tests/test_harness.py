"""Tests for the deterministic agent harness."""

import json

import pytest

from governed_agent.checks import Check, CheckResult
from governed_agent.harness import Agent, AgentConfig
from governed_agent.models import ScriptedModel


def _j(obj):
    return json.dumps(obj)


def _audit_events(run):
    return [json.loads(line) for line in run.audit_path.read_text().splitlines() if line.strip()]


def _manifest(run):
    path = run.audit_path.with_name(run.audit_path.name.replace(".jsonl", ".manifest.json"))
    return json.loads(path.read_text())


def test_agent_completes_scripted_run(tmp_path):
    script = [
        _j({"tool": "list_dir", "args": {"path": "."}}),
        _j({"done": True, "result": "all good"}),
    ]
    agent = Agent(ScriptedModel(script=script), tmp_path, audit_dir=tmp_path / "audit")
    run = agent.run("list the repo")
    assert run.status == "finished"
    assert run.result == "all good"
    assert run.model_calls == 2
    manifest = _manifest(run)
    assert manifest["model"]["model"] == "scripted-demo-v1"
    assert manifest["model"]["backend"] == "scripted"
    assert manifest["seed"] == 0
    assert "list_dir" in manifest["tools"]
    assert manifest["outcome"] == "finished"
    events = _audit_events(run)
    assert events[0]["event"] == "run_started"
    assert events[-1]["event"] == "run_manifest"
    assert all(e["run_id"] == run.run_id for e in events)
    kinds = {e["event"] for e in events}
    assert {"model_call", "tool_call", "tool_result", "checks"} <= kinds


def test_max_steps_stops_the_run(tmp_path):
    script = [
        _j({"tool": "list_dir", "args": {"path": "."}}),
        _j({"tool": "list_dir", "args": {"path": "."}}),
        _j({"tool": "list_dir", "args": {"path": "."}}),
        _j({"done": True, "result": "never reached"}),
    ]
    agent = Agent(
        ScriptedModel(script=script),
        tmp_path,
        config=AgentConfig(max_steps=2),
        audit_dir=tmp_path / "audit",
    )
    run = agent.run("do things")
    assert run.status == "budget_exceeded"
    assert len(run.steps) == 2
    assert run.model_calls == 2


def test_max_model_calls_stops_the_run(tmp_path):
    script = [_j({"tool": "list_dir", "args": {"path": "."}})] * 5
    agent = Agent(
        ScriptedModel(script=script),
        tmp_path,
        config=AgentConfig(max_steps=10, max_model_calls=3),
        audit_dir=tmp_path / "audit",
    )
    run = agent.run("do things")
    assert run.status == "budget_exceeded"
    assert run.model_calls == 3
    assert len(run.steps) == 3


class AlwaysStop(Check):
    name = "always_stop"
    stops_run = True

    def run(self, context):
        return CheckResult(False, self.name, "policy: no writes ever")


def test_fatal_check_stops_the_run(tmp_path):
    script = [_j({"tool": "list_dir", "args": {"path": "."}})]
    agent = Agent(
        ScriptedModel(script=script),
        tmp_path,
        checks=[AlwaysStop()],
        audit_dir=tmp_path / "audit",
    )
    run = agent.run("list")
    assert run.status == "check_failed"
    assert run.steps == []
    assert "policy: no writes ever" in run.result
    events = _audit_events(run)
    assert any(e["event"] == "run_stopped" and e["outcome"] == "check_failed" for e in events)


class Flaky(Check):
    name = "flaky"
    stops_run = False

    def __init__(self):
        self.calls = 0

    def run(self, context):
        self.calls += 1
        if self.calls == 1:
            return CheckResult(False, self.name, "first attempt rejected")
        return CheckResult(True, self.name)


def test_retryable_check_retries_and_continues(tmp_path):
    script = [
        _j({"tool": "draft_finding", "args": {"title": "t", "file": "f.py", "line": 1, "evidence": "x", "confidence": "high"}}),
        _j({"tool": "draft_finding", "args": {"title": "t", "file": "f.py", "line": 1, "evidence": "x", "confidence": "high"}}),
        _j({"done": True, "result": "done"}),
    ]
    agent = Agent(ScriptedModel(script=script), tmp_path, checks=[Flaky()], audit_dir=tmp_path / "audit")
    run = agent.run("draft")
    assert run.status == "finished"
    drafted = [s for s in run.steps if s["tool"] == "draft_finding"]
    assert len(drafted) == 1
    assert drafted[0]["result"]["title"] == "t"
    events = _audit_events(run)
    assert any(e["event"] == "check_retry" for e in events)


def test_tool_not_on_allowlist_is_blocked(tmp_path):
    # A mutating call with no approval is stopped by the approval check
    # before it ever reaches the tool — that is the governed behaviour.
    (tmp_path / "f.py").write_text("x = 1\n")
    script = [
        _j({"tool": "write_file", "args": {"path": "f.py", "content": "x = 2\n"}}),
        _j({"done": True, "result": "done"}),
    ]
    agent = Agent(ScriptedModel(script=script), tmp_path, audit_dir=tmp_path / "audit")
    run = agent.run("write")
    assert run.status == "check_failed"
    assert (tmp_path / "f.py").read_text() == "x = 1\n"
    assert "without human approval" in run.result


def test_allowlist_enforced_at_registry_level(tmp_path):
    from governed_agent.tools import ToolContext, ToolError, ToolRegistry

    registry = ToolRegistry(allowlist=["read_file"])
    ctx = ToolContext(repo_root=tmp_path)
    with pytest.raises(ToolError, match="not on this run's allowlist"):
        registry.call("write_file", {"path": "f.py", "content": "x = 2\n"}, ctx)


def test_write_gate_blocks_without_allow_write(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\n")
    script = [
        _j({"tool": "write_file", "args": {"path": "f.py", "content": "x = 2\n"}}),
        _j({"done": True, "result": "done"}),
    ]
    agent = Agent(
        ScriptedModel(script=script),
        tmp_path,
        config=AgentConfig(allowlist=["write_file"], approve=lambda action: True),
        allow_write=False,
        audit_dir=tmp_path / "audit",
    )
    run = agent.run("write")
    assert (tmp_path / "f.py").read_text() == "x = 1\n"
    events = _audit_events(run)
    assert any(
        e["event"] == "tool_error" and "read-only" in e["error"] for e in events
    )


def test_write_gate_allows_with_approval(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\n")
    script = [
        _j({"tool": "write_file", "args": {"path": "f.py", "content": "x = 2\n"}}),
        _j({"done": True, "result": "done"}),
    ]
    agent = Agent(
        ScriptedModel(script=script),
        tmp_path,
        config=AgentConfig(allowlist=["write_file"], approve=lambda action: True),
        allow_write=True,
        audit_dir=tmp_path / "audit",
    )
    run = agent.run("write")
    assert run.status == "finished"
    assert (tmp_path / "f.py").read_text() == "x = 2\n"


def test_approval_denied_blocks_write(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\n")
    script = [
        _j({"tool": "write_file", "args": {"path": "f.py", "content": "x = 2\n"}}),
        _j({"done": True, "result": "done"}),
    ]
    agent = Agent(
        ScriptedModel(script=script),
        tmp_path,
        config=AgentConfig(allowlist=["write_file"], approve=lambda action: False),
        allow_write=True,
        audit_dir=tmp_path / "audit",
    )
    run = agent.run("write")
    assert run.status == "check_failed"
    assert (tmp_path / "f.py").read_text() == "x = 1\n"
    assert "without human approval" in run.result


def test_path_confinement_blocks_escape(tmp_path):
    script = [
        _j({"tool": "read_file", "args": {"path": "../outside.txt"}}),
        _j({"done": True, "result": "done"}),
    ]
    agent = Agent(ScriptedModel(script=script), tmp_path, audit_dir=tmp_path / "audit")
    run = agent.run("read")
    events = _audit_events(run)
    assert any(
        e["event"] == "tool_error" and "escapes the repo root" in e["error"] for e in events
    )
