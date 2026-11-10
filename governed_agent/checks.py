"""Governed checks: rules that CAN stop a run.

A check is a rule with a verdict. If a check fails, the harness either
retries the step (bounded) or stops the run — a check that cannot stop
the run is not a check, it is a comment. Every check outcome is
written to the audit log.

Checks shipped here:
- NoWriteWithoutApproval: a mutating tool call without approval fails.
- CitationRequired: a draft finding must cite a real file/line that
  exists in the repo, with evidence text.
- MaxSteps / MaxModelCalls: budget checks, enforced by the harness.
- NoSecretsInOutput: a finding must not contain a plausible secret
  (API-key-shaped strings).
- EvidenceMatchesFile: a finding's evidence text must actually appear
  in the cited file (guards against hallucinated citations).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    passed: bool
    check: str
    reason: str = ""
    detail: dict = field(default_factory=dict)


class Check:
    """One rule. `run` returns a CheckResult; `stops_run` says whether
    a failure stops the run (True) or only triggers a retry (False)."""

    name: str = "check"
    stops_run: bool = True

    def run(self, context: dict) -> CheckResult:
        raise NotImplementedError


_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?"
    r"|sk-[A-Za-z0-9]{16,}"
    r"|ghp_[A-Za-z0-9]{20,}"
)


class NoWriteWithoutApproval(Check):
    name = "no_write_without_approval"
    stops_run = True

    def run(self, context: dict) -> CheckResult:
        if context.get("tool", {}).get("mutates") and not context.get("approved", False):
            return CheckResult(False, self.name, "mutating tool call without human approval")
        return CheckResult(True, self.name)


class CitationRequired(Check):
    """A draft finding must cite an existing file and line."""

    name = "citation_required"
    stops_run = False  # bad finding -> retry, do not kill the whole run

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run(self, context: dict) -> CheckResult:
        if context.get("tool", {}).get("name") != "draft_finding":
            return CheckResult(True, self.name)
        args = context.get("args", {})
        rel = str(args.get("file", ""))
        line = args.get("line")
        if not rel or line is None:
            return CheckResult(False, self.name, "finding has no file/line citation")
        path = self.repo_root / rel
        if not path.is_file():
            return CheckResult(False, self.name, f"cited file does not exist: {rel}")
        try:
            total = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError as exc:
            return CheckResult(False, self.name, f"cited file unreadable: {exc}")
        if not (1 <= int(line) <= max(total, 1)):
            return CheckResult(False, self.name, f"cited line {line} out of range (1..{total})")
        if not str(args.get("evidence", "")).strip():
            return CheckResult(False, self.name, "finding has no evidence text")
        return CheckResult(True, self.name)


class EvidenceMatchesFile(Check):
    """The finding's evidence must actually appear in the cited file."""

    name = "evidence_matches_file"
    stops_run = False

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run(self, context: dict) -> CheckResult:
        if context.get("tool", {}).get("name") != "draft_finding":
            return CheckResult(True, self.name)
        args = context.get("args", {})
        rel = str(args.get("file", ""))
        evidence = str(args.get("evidence", "")).strip()
        if not rel or not evidence:
            return CheckResult(False, self.name, "finding has no file/evidence to match")
        path = self.repo_root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return CheckResult(False, self.name, f"cited file unreadable: {exc}")
        # Match on the first 40 non-space characters of the evidence.
        probe = " ".join(evidence.split())[:40]
        if probe and probe not in " ".join(text.split()):
            return CheckResult(
                False,
                self.name,
                "evidence text does not appear in the cited file (possible hallucinated citation)",
            )
        return CheckResult(True, self.name)


class NoSecretsInOutput(Check):
    name = "no_secrets_in_output"
    stops_run = True

    def run(self, context: dict) -> CheckResult:
        blob = str(context.get("args", {}))
        if _SECRET_RE.search(blob):
            return CheckResult(False, self.name, "output looks like it contains a secret")
        return CheckResult(True, self.name)


class BudgetCheck(Check):
    """Step / model-call budget. Enforced by the harness each step."""

    name = "budget"
    stops_run = True

    def __init__(self, max_steps: int, max_model_calls: int):
        self.max_steps = max_steps
        self.max_model_calls = max_model_calls

    def run(self, context: dict) -> CheckResult:
        if context.get("step", 0) > self.max_steps:
            return CheckResult(False, self.name, f"step budget exceeded ({self.max_steps})")
        if context.get("model_calls", 0) > self.max_model_calls:
            return CheckResult(False, self.name, f"model-call budget exceeded ({self.max_model_calls})")
        return CheckResult(True, self.name)


def default_checks(repo_root: Path, max_steps: int, max_model_calls: int) -> list[Check]:
    """The standard check set for a governed run."""
    return [
        NoWriteWithoutApproval(),
        CitationRequired(repo_root),
        EvidenceMatchesFile(repo_root),
        NoSecretsInOutput(),
        BudgetCheck(max_steps, max_model_calls),
    ]
