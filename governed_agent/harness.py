"""The deterministic agent harness: task + context -> plan -> act -> observe -> check -> finish.

Loop, per step:
1. Plan: one model call. The model returns either a tool call
   ({"tool": name, "args": {...}}) or done ({"done": true, ...}).
   Malformed model output is tolerated: the parser retries the call
   once with a repair prompt, then records a parse failure and stops
   that step (small models produce malformed JSON; the harness must
   not crash on it).
2. Act: exactly one tool call, and only if the tool is on the
   allowlist. A mutating tool requires human approval first; without
   it the check fails and the run stops.
3. Observe: the tool result goes into the history.
4. Check: every check runs against the planned action. A failing
   check that stops the run ends the run immediately; a failing
   retryable check discards the action and retries (bounded).

Budgets: max_steps and max_model_calls are hard stops. The run
manifest + audit log record everything needed to reproduce the run.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from governed_agent.audit import AuditLog, RunManifest
from governed_agent.checks import Check, default_checks
from governed_agent.models import ModelBackend
from governed_agent.tools import ToolContext, ToolError, ToolRegistry


@dataclass
class AgentConfig:
    max_steps: int = 8
    max_model_calls: int = 12
    max_check_retries: int = 2
    seed: int = 0
    # Approval: a callable(action: dict) -> bool. None = deny everything
    # mutating. Evals may pass an approver that approves only writes
    # inside a sandbox temp dir; the default denies.
    approve: object = None
    allowlist: list[str] | None = None


@dataclass
class AgentRun:
    run_id: str
    status: str  # finished | stopped | check_failed | budget_exceeded | error
    steps: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    result: str = ""
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    manifest: RunManifest | None = None
    audit_path: Path | None = None


# Tolerate small-model malformed output: find the first {...} block.
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_decision(text: str) -> dict:
    """Parse a model decision. Returns {"tool": ..., "args": ...} or
    {"done": True, ...}. Raises ValueError on unparseable output."""
    text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_RE.search(text)
        if not match:
            raise ValueError(f"model output is not JSON: {text[:200]!r}")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model decision is not an object")
    if data.get("done"):
        return {"done": True, "result": str(data.get("result", ""))}
    if "tool" not in data:
        raise ValueError("model decision has neither 'done' nor 'tool'")
    return {"tool": str(data["tool"]), "args": data.get("args") or {}}


class Agent:
    """One governed agent run."""

    def __init__(
        self,
        model: ModelBackend,
        repo_root: Path,
        config: AgentConfig | None = None,
        registry: ToolRegistry | None = None,
        checks: list[Check] | None = None,
        audit_dir: Path | None = None,
        allow_write: bool = False,
    ):
        self.model = model
        self.repo_root = Path(repo_root)
        self.config = config or AgentConfig()
        self.registry = registry or ToolRegistry(allowlist=self.config.allowlist)
        self.checks = checks if checks is not None else default_checks(
            self.repo_root, self.config.max_steps, self.config.max_model_calls
        )
        self.audit_dir = Path(audit_dir) if audit_dir else Path.cwd() / ".governed_runs"
        # allow_write is a second gate at the tool layer, in addition to
        # the approval callback. It is False unless the caller explicitly
        # enables it (e.g. an eval sandbox on a temp copy).
        self.tool_ctx = ToolContext(repo_root=self.repo_root, allow_write=allow_write)

    # -- internals -----------------------------------------------------
    def _approve(self, action: dict) -> bool:
        approve = self.config.approve
        if approve is None:
            return False
        return bool(approve(action))

    def _run_checks(self, context: dict) -> list:
        results = []
        for check in self.checks:
            result = check.run(context)
            results.append(result)
        return results

    # -- public --------------------------------------------------------
    def run(self, task: str, context: str = "") -> AgentRun:
        run_id = uuid.uuid4().hex[:12]
        audit_path = self.audit_dir / f"run-{run_id}.jsonl"
        manifest_path = self.audit_dir / f"run-{run_id}.manifest.json"
        audit = AuditLog(audit_path, run_id)
        manifest = RunManifest.build(
            run_id=run_id,
            task=task,
            model_desc=self.model.describe(),
            tools=self.registry.allowlist,
            checks=[c.name for c in self.checks],
            seed=self.config.seed,
            max_steps=self.config.max_steps,
            max_model_calls=self.config.max_model_calls,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a governed agent. You may only call the tools listed. "
                    "Return exactly one JSON object per turn: either "
                    '{"tool": "<name>", "args": {...}} or {"done": true, "result": "<summary>"}. '
                    "Do one thing per step. Never send, delete, buy, or publish anything. "
                    "If you cannot verify a claim from a tool result, say so."
                ),
            },
            {"role": "user", "content": f"Task: {task}\nContext:\n{context}"},
        ]
        audit.event("run_started", task=task, task_hash=manifest.task_hash, model=manifest.model)
        run = AgentRun(run_id=run_id, status="error", audit_path=audit_path, manifest=manifest)
        history: list[dict] = []
        steps: list[dict] = []
        check_retries = 0

        for step in range(1, self.config.max_steps + 1):
            if run.model_calls >= self.config.max_model_calls:
                run.status = "budget_exceeded"
                audit.event("budget_exceeded", reason="model-call budget")
                break
            # --- plan ---
            try:
                resp = self.model.complete(messages)
            except Exception as exc:  # model unreachable / no key
                run.status = "error"
                run.result = f"model error: {exc}"
                audit.event("model_error", error=str(exc))
                break
            run.model_calls += 1
            run.tokens_in += resp.tokens_in
            run.tokens_out += resp.tokens_out
            run.latency_ms += resp.latency_ms
            audit.event("model_call", step=step, text=resp.text[:2000], tokens_in=resp.tokens_in, tokens_out=resp.tokens_out)
            messages.append({"role": "assistant", "content": resp.text})
            # --- parse (tolerant, one repair retry) ---
            try:
                decision = parse_decision(resp.text)
            except ValueError:
                audit.event("parse_failed", step=step, text=resp.text[:500])
                if run.model_calls >= self.config.max_model_calls:
                    run.status = "budget_exceeded"
                    break
                repair = self.model.complete(
                    messages
                    + [{"role": "user", "content": "That was not valid JSON. Reply with exactly one JSON object: {\"tool\": \"<name>\", \"args\": {...}} or {\"done\": true, \"result\": \"...\"}."}]
                )
                run.model_calls += 1
                run.tokens_in += repair.tokens_in
                run.tokens_out += repair.tokens_out
                try:
                    decision = parse_decision(repair.text)
                except ValueError:
                    run.status = "error"
                    run.result = "model output unparseable after repair"
                    audit.event("parse_failed", step=step, text=repair.text[:500], fatal=True)
                    break
            if decision.get("done"):
                run.status = "finished"
                run.result = str(decision.get("result", ""))
                audit.event("run_finished", outcome="finished", result=run.result[:500])
                break
            # --- checks before acting ---
            tool_name = decision["tool"]
            args = decision["args"]
            mutates = self.registry.is_mutating(tool_name)
            approved = False
            if mutates:
                approved = self._approve({"tool": tool_name, "args": args})
                audit.event("approval_requested", step=step, tool=tool_name, approved=approved)
            ctx = {
                "step": step,
                "model_calls": run.model_calls,
                "tool": {"name": tool_name, "mutates": mutates},
                "args": args,
                "approved": approved,
            }
            check_results = self._run_checks(ctx)
            failed = [r for r in check_results if not r.passed]
            audit.event(
                "checks",
                step=step,
                tool=tool_name,
                results=[{"check": r.check, "passed": r.passed, "reason": r.reason} for r in check_results],
            )
            if failed:
                blocking = [r for r in failed if next(c for c in self.checks if c.name == r.check).stops_run]
                if blocking:
                    run.status = "check_failed"
                    run.result = "; ".join(f"{r.check}: {r.reason}" for r in blocking)
                    audit.event("run_stopped", outcome="check_failed", reason=run.result)
                    break
                check_retries += 1
                if check_retries > self.config.max_check_retries:
                    run.status = "check_failed"
                    run.result = "too many failed checks: " + "; ".join(r.reason for r in failed)
                    audit.event("run_stopped", outcome="check_failed", reason=run.result)
                    break
                messages.append({"role": "user", "content": "That action failed a check: " + "; ".join(r.reason for r in failed) + ". Try a different action."})
                audit.event("check_retry", step=step, reasons=[r.reason for r in failed])
                continue
            # --- act ---
            try:
                result = self.registry.call(tool_name, args, self.tool_ctx)
            except ToolError as exc:
                audit.event("tool_error", step=step, tool=tool_name, error=str(exc))
                messages.append({"role": "user", "content": f"Tool {tool_name} failed: {exc}. Try a different action."})
                continue
            step_record = {"step": step, "tool": tool_name, "args": args, "result": result}
            steps.append(step_record)
            history.append(step_record)
            audit.event("tool_call", step=step, tool=tool_name, args=args)
            audit.event("tool_result", step=step, tool=tool_name, result=str(result)[:2000])
            messages.append({"role": "user", "content": f"Tool result: {json.dumps(result)[:2000]}"})
        else:
            run.status = "budget_exceeded"
            audit.event("budget_exceeded", reason="step budget")

        if run.status == "error" and not run.result:
            run.result = "run ended without finishing"
        run.steps = steps
        run.history = history
        manifest.outcome = run.status
        manifest.finished_at = audit.event("run_manifest", outcome=run.status)["ts"]
        manifest.counts = {
            "steps": len(steps),
            "model_calls": run.model_calls,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
            "latency_ms": round(run.latency_ms, 1),
        }
        manifest_path.write_text(manifest.to_json(), encoding="utf-8")
        return run
