"""Audit log + run manifest: the auditable record of every run.

- AuditLog: append-only JSONL. One line per event (run started,
  model call, tool call, tool result, check outcome, approval
  request/decision, run finished). Every line carries a timestamp, the
  run id, and the event payload.
- RunManifest: the reproducibility record for a run — model, prompt/task
  hash, tools, versions, seed, budgets, and outcome. Written as JSON
  next to the audit log.

A stranger with the manifest + the audit log + the repo at the recorded
commit can re-run the task and compare outcomes. That is the point.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from governed_agent import __version__ as _pkg_version


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class RunManifest:
    run_id: str
    task: str
    task_hash: str
    model: dict
    tools: list[str]
    checks: list[str]
    seed: int
    max_steps: int
    max_model_calls: int
    started_at: str
    versions: dict = field(default_factory=dict)
    outcome: str = "unknown"
    finished_at: str = ""
    counts: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def build(
        cls,
        run_id: str,
        task: str,
        model_desc: dict,
        tools: list[str],
        checks: list[str],
        seed: int,
        max_steps: int,
        max_model_calls: int,
    ) -> "RunManifest":
        return cls(
            run_id=run_id,
            task=task,
            task_hash=_sha256_text(task),
            model=model_desc,
            tools=sorted(tools),
            checks=sorted(checks),
            seed=seed,
            max_steps=max_steps,
            max_model_calls=max_model_calls,
            started_at=_now_iso(),
            versions={
                "governed_agent": _pkg_version,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
        )


class AuditLog:
    """Append-only JSONL audit log for one run."""

    def __init__(self, path: Path, run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._events = 0

    def event(self, kind: str, **payload) -> dict:
        record = {
            "ts": _now_iso(),
            "run_id": self.run_id,
            "event": kind,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        self._events += 1
        return record

    @property
    def events(self) -> int:
        return self._events

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
