"""Evidence-first repo reviewer, on top of the governed harness.

The reviewer drives the harness with read-only tools and drafts
findings. Every finding must cite file/line/commit/test, carry a
confidence grade (high/medium/low) or an explicit "cannot verify"
state, and be backed by evidence text that actually appears in the
cited file (enforced by the harness checks). The reviewer drafts
findings only: it never sends, deletes, publishes, or writes to the
reviewed repo.

Confidence rules (documented, deterministic):
- high: a test fails at the cited line, or the cited code contradicts
  its own docstring/contract in a way a test demonstrates.
- medium: a code pattern contradicts the contract but no failing test
  demonstrates it yet.
- low: a suspicion with a citation but no demonstration.
- cannot_verify: the claim cannot be checked from the repo (missing
  test, missing file, gated dependency).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from governed_agent.harness import Agent, AgentConfig
from governed_agent.models import ModelBackend


@dataclass
class Finding:
    title: str
    file: str
    line: int
    evidence: str
    confidence: str  # high | medium | low | cannot_verify
    severity: str = "medium"
    test: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        return (
            f"### {self.title}\n\n"
            f"- **Location:** `{self.file}:{self.line}`\n"
            f"- **Severity:** {self.severity} · **Confidence:** {self.confidence}\n"
            + (f"- **Test:** `{self.test}`\n" if self.test else "")
            + f"- **Evidence:**\n\n```\n{self.evidence}\n```\n"
        )


@dataclass
class ReviewReport:
    repo: str
    run_id: str
    status: str
    findings: list[Finding] = field(default_factory=list)
    audit_path: Path | None = None
    manifest_path: Path | None = None

    def to_markdown(self) -> str:
        lines = [
            f"# Review: {self.repo}",
            "",
            f"Run: `{self.run_id}` · Status: {self.status}",
            "",
            f"Findings: {len(self.findings)}",
            "",
        ]
        if not self.findings:
            lines.append("No findings. Nothing in the repo could be verified as a defect from the evidence gathered.")
            lines.append("")
            lines.append("That is a statement about the evidence gathered, not a proof the repo is defect-free.")
        for f in self.findings:
            lines.append(f.to_markdown())
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "repo": self.repo,
                "run_id": self.run_id,
                "status": self.status,
                "findings": [f.to_dict() for f in self.findings],
            },
            indent=2,
        )


def _findings_from_history(history: list[dict]) -> list[Finding]:
    """Collect draft_finding tool results from the run history."""
    findings: list[Finding] = []
    for step in history:
        if step.get("tool") != "draft_finding":
            continue
        result = step.get("result") or {}
        if not isinstance(result, dict) or "title" not in result:
            continue
        findings.append(
            Finding(
                title=str(result["title"]),
                file=str(result["file"]),
                line=int(result["line"]),
                evidence=str(result["evidence"]),
                confidence=str(result["confidence"]),
                severity=str(result.get("severity", "medium")),
            )
        )
    return findings


def review_repo(
    repo_path: Path,
    model: ModelBackend,
    task: str | None = None,
    config: AgentConfig | None = None,
    audit_dir: Path | None = None,
    checks: list | None = None,
) -> ReviewReport:
    """Run an evidence-first review of `repo_path` with `model`.

    The agent is read-only: the allowlist excludes write_file, and no
    approval callback is provided, so any mutating call fails the
    no_write_without_approval check and stops the run.
    """
    repo_path = Path(repo_path)
    task = task or (
        "Review this repository for defects. Read the code, run its tests, "
        "and draft a finding for each defect you can demonstrate from the "
        "evidence, citing file and line and grading your confidence. "
        "If you cannot verify a suspicion, draft it as cannot_verify or say so."
    )
    agent = Agent(model, repo_path, config=config or AgentConfig(), audit_dir=audit_dir, checks=checks)
    run = agent.run(task)
    findings = _findings_from_history(run.history)
    # Attach the failing-test evidence to findings that match a test failure.
    for step in run.history:
        if step.get("tool") == "run_tests":
            output = str(step.get("result", {}).get("output", ""))
            for finding in findings:
                if finding.file in output or finding.title.lower() in output.lower():
                    if not finding.test:
                        finding.test = "see audit log tool_result for run_tests"
    manifest_path = None
    if run.audit_path is not None:
        manifest_path = run.audit_path.with_name(run.audit_path.name.replace(".jsonl", ".manifest.json"))
    return ReviewReport(
        repo=str(repo_path),
        run_id=run.run_id,
        status=run.status,
        findings=findings,
        audit_path=run.audit_path,
        manifest_path=manifest_path,
    )
