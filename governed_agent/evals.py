"""The Phase 1 eval suite: held-out tasks, ablations, pass@k, review quality.

What this measures, honestly:
- The demo model is scripted (seeded behaviours: correct / noisy /
  sloppy). These evals measure the HARNESS — budgets, checks, and
  ablations — not model capability. A real model (Ollama/cloud) plugs
  into the same runner and the same tasks.
- Fix tasks: the agent must make the fixture's tests pass in a temp
  copy. Writes are allowed only inside that temp dir (sandbox-scoped
  approval + tool-layer write gate). Pass = pytest exit 0 afterwards.
- Review tasks: the agent reviews a fixture and drafts findings.
  Graded against the known injected bugs: precision, recall, and the
  false-positive rate. One fixture is clean — any finding there is a
  false positive.
- Ablation: the same model and tasks under different harness settings
  (baseline / low step budget / checks disabled), so the harness's
  contribution is measurable instead of asserted.

Task integrity: every task carries a sha256 hash over its canonical
record (id, kind, description, fixture file bytes). The runner
verifies hashes before running and refuses to run a tampered set.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from governed_agent.harness import Agent, AgentConfig
from governed_agent.models import ModelBackend, ScriptedModel
from governed_agent.reviewer import review_repo
from governed_agent.tools import READONLY_ALLOWLIST

FIXTURE_FILES = ("target.py", "test_target.py")


def canonical_task_hash(task: dict, fixtures_root: Path) -> str:
    """sha256 of the canonical task record (id, kind, description, fixture bytes)."""
    fixture_dir = Path(fixtures_root) / task["fixture"]
    files = {}
    for name in FIXTURE_FILES:
        path = fixture_dir / name
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    record = {
        "id": task["id"],
        "kind": task["kind"],
        "description": task["description"],
        "files": files,
    }
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest()


def load_tasks(tasks_path: Path, fixtures_root: Path) -> list[dict]:
    """Load the task set and verify every task hash. Refuses tampered sets."""
    data = json.loads(Path(tasks_path).read_text(encoding="utf-8"))
    tasks = []
    for task in data["tasks"]:
        expected = task.get("hash", "")
        actual = canonical_task_hash(task, fixtures_root)
        if expected != actual:
            raise ValueError(
                f"task {task['id']}: hash mismatch (recorded {expected[:12]!r}, computed {actual[:12]!r}). "
                "The task set may have been edited — re-hash it before running."
            )
        tasks.append(task)
    return tasks


# -- scripted demo behaviour -------------------------------------------
def _json_decision(obj: dict) -> str:
    return json.dumps(obj)


def _fixture_line(fixture_dir: Path, line_no: int) -> str:
    lines = (fixture_dir / "target.py").read_text(encoding="utf-8").splitlines()
    return lines[line_no - 1].strip() if 0 < line_no <= len(lines) else ""


def build_fix_script(task: dict, seed: int) -> list[str]:
    """Scripted model behaviour for a fix task, by seed."""
    if seed == 0:
        fix_content = task["solution"]
    elif seed == 1:
        fix_content = task["wrong_fix"]
    else:  # seed 2: sloppy — never attempts a fix
        return [
            _json_decision({"tool": "read_file", "args": {"path": "target.py"}}),
            _json_decision({"tool": "run_tests", "args": {"path": "."}}),
            _json_decision({"done": True, "result": "looked at the code; no fix attempted"}),
        ]
    return [
        _json_decision({"tool": "read_file", "args": {"path": "target.py"}}),
        _json_decision({"tool": "run_tests", "args": {"path": "."}}),
        _json_decision({"tool": "write_file", "args": {"path": "target.py", "content": fix_content}}),
        _json_decision({"tool": "run_tests", "args": {"path": "."}}),
        _json_decision({"done": True, "result": "fix applied; tests re-run"}),
    ]


def build_review_script(task: dict, seed: int, fixture_dir: Path) -> list[str]:
    """Scripted model behaviour for a review task, by seed."""
    steps = [
        _json_decision({"tool": "read_file", "args": {"path": "target.py"}}),
        _json_decision({"tool": "run_tests", "args": {"path": "."}}),
    ]
    bugs = task.get("known_bugs", [])
    if seed == 0:
        for bug in bugs:
            steps.append(
                _json_decision(
                    {
                        "tool": "draft_finding",
                        "args": {
                            "title": bug["title"],
                            "file": bug["file"],
                            "line": bug["line"],
                            "evidence": _fixture_line(fixture_dir, bug["line"]),
                            "confidence": "high",
                            "severity": "high",
                        },
                    }
                )
            )
    elif seed == 1:
        for bug in bugs:
            steps.append(
                _json_decision(
                    {
                        "tool": "draft_finding",
                        "args": {
                            "title": bug["title"],
                            "file": bug["file"],
                            "line": bug["line"],
                            "evidence": _fixture_line(fixture_dir, bug["line"]),
                            "confidence": "high",
                            "severity": "high",
                        },
                    }
                )
            )
        # Noisy extra: a well-cited finding about a non-bug (false positive).
        steps.append(
            _json_decision(
                {
                    "tool": "draft_finding",
                    "args": {
                        "title": "Module docstring may be incomplete",
                        "file": "target.py",
                        "line": 1,
                        "evidence": _fixture_line(fixture_dir, 1),
                        "confidence": "low",
                        "severity": "low",
                    },
                }
            )
        )
    else:  # seed 2: sloppy — a finding with a fake citation
        steps.append(
            _json_decision(
                {
                    "tool": "draft_finding",
                    "args": {
                        "title": "Hidden defect in helper",
                        "file": "target.py",
                        "line": 999,
                        "evidence": "def secret(): pass",
                        "confidence": "medium",
                        "severity": "high",
                    },
                }
            )
        )
    steps.append(_json_decision({"done": True, "result": "review complete"}))
    return steps


# -- grading ------------------------------------------------------------
def grade_fix(work_dir: Path) -> bool:
    """Pass = the fixture's tests pass in the working copy."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "."],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(work_dir),
    )
    return proc.returncode == 0


def grade_review(findings: list[dict], known_bugs: list[dict]) -> dict:
    """Precision/recall against known bugs; matches are (file, line)."""
    known = {(b["file"], b["line"]) for b in known_bugs}
    tp = sum(1 for f in findings if (f.get("file"), f.get("line")) in known)
    fp = len(findings) - tp
    precision = (tp / len(findings)) if findings else None
    recall = (tp / len(known)) if known else None
    return {
        "true_positives": tp,
        "false_positives": fp,
        "precision": precision,
        "recall": recall,
        "known_bugs": len(known),
        "findings": len(findings),
    }


def pass_at_k(n: int, c: int, k: int) -> float:
    """Standard pass@k estimator: 1 - C(n-c, k) / C(n, k)."""
    if c == 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


# -- settings -----------------------------------------------------------
@dataclass
class EvalSetting:
    name: str
    max_steps: int = 8
    max_model_calls: int = 12
    checks: str = "on"  # "on" | "off"


SETTINGS = [
    EvalSetting("baseline", 8, 12, "on"),
    EvalSetting("low_budget", 3, 4, "on"),
    EvalSetting("no_checks", 8, 12, "off"),
]


def _sandbox_approver(root: Path):
    """Approve writes only inside `root` (eval sandbox)."""
    root = root.resolve()

    def approve(action: dict) -> bool:
        if action.get("tool") != "write_file":
            return False
        rel = str(action.get("args", {}).get("path", ""))
        try:
            target = (root / rel).resolve()
        except Exception:
            return False
        return target == root or root in target.parents

    return approve


def _manifest_path(audit_path) -> str:
    if not audit_path:
        return ""
    path = Path(audit_path)
    return str(path.with_name(path.name.replace(".jsonl", ".manifest.json")))


def _cost_usd(model: ModelBackend, tokens_in: int, tokens_out: int):
    """Cost in USD, or None when unknown (no price configured / local)."""
    cost_fn = getattr(model, "cost_usd", None)
    if cost_fn is None:
        return 0.0
    return cost_fn(tokens_in, tokens_out)


def _run_fix_task(
    task: dict,
    seed: int,
    setting: EvalSetting,
    fixtures_root: Path,
    audit_dir: Path,
    model: ModelBackend,
) -> dict:
    fixture_dir = Path(fixtures_root) / task["fixture"]
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ga-eval-") as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(fixture_dir, work)
        config = AgentConfig(
            max_steps=setting.max_steps,
            max_model_calls=setting.max_model_calls,
            seed=seed,
            approve=_sandbox_approver(work),
            allowlist=READONLY_ALLOWLIST + ["write_file"],
        )
        checks = None if setting.checks == "on" else []
        agent = Agent(model, work, config=config, audit_dir=audit_dir, checks=checks, allow_write=True)
        run = agent.run(task["description"])
        passed = grade_fix(work)
        audit_path = str(run.audit_path) if run.audit_path else ""
        manifest_path = _manifest_path(run.audit_path)
        cost = _cost_usd(model, run.tokens_in, run.tokens_out)
    return {
        "task": task["id"],
        "kind": "fix",
        "seed": seed,
        "setting": setting.name,
        "passed": passed,
        "status": run.status,
        "model_calls": run.model_calls,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "latency_ms": round(run.latency_ms, 1),
        "cost_usd": cost,
        "steps": len(run.steps),
        "run_id": run.run_id,
        "audit_path": audit_path,
        "manifest_path": manifest_path,
        "wall_ms": round((time.monotonic() - start) * 1000, 1),
    }


def _run_review_task(
    task: dict,
    seed: int,
    setting: EvalSetting,
    fixtures_root: Path,
    audit_dir: Path,
    model: ModelBackend,
) -> dict:
    fixture_dir = Path(fixtures_root) / task["fixture"]
    start = time.monotonic()
    config = AgentConfig(max_steps=setting.max_steps, max_model_calls=setting.max_model_calls, seed=seed)
    checks = None if setting.checks == "on" else []
    report = review_repo(fixture_dir, model, config=config, audit_dir=audit_dir, checks=checks)
    grading = grade_review([f.to_dict() for f in report.findings], task.get("known_bugs", []))
    return {
        "task": task["id"],
        "kind": "review",
        "seed": seed,
        "setting": setting.name,
        "passed": bool(grading["recall"] == 1.0 and grading["precision"] == 1.0),
        "status": report.status,
        "model_calls": None,
        "tokens_in": None,
        "tokens_out": None,
        "latency_ms": None,
        "cost_usd": 0.0,
        "steps": len(report.findings),
        "run_id": report.run_id,
        "audit_path": str(report.audit_path) if report.audit_path else "",
        "manifest_path": str(report.manifest_path) if report.manifest_path else "",
        "wall_ms": round((time.monotonic() - start) * 1000, 1),
        "review": grading,
        "findings": [f.to_dict() for f in report.findings],
    }


def default_model_factory(task: dict, seed: int, fixtures_root: Path) -> ModelBackend:
    """The scripted demo model for a task/seed (the default factory)."""
    fixture_dir = Path(fixtures_root) / task["fixture"]
    if task["kind"] == "fix":
        return ScriptedModel(script=build_fix_script(task, seed), seed=seed)
    return ScriptedModel(script=build_review_script(task, seed, fixture_dir), seed=seed)


def run_suite(
    tasks_path: Path,
    fixtures_root: Path,
    results_dir: Path,
    seeds: list[int] | None = None,
    settings: list[EvalSetting] | None = None,
    model_note: str = "scripted-demo-v1 (seeded behaviours: 0=correct, 1=noisy, 2=sloppy)",
    model_factory=None,
) -> dict:
    """Run the full suite: all tasks x seeds x settings. Writes raw logs
    and a results table. Returns the summary dict.

    `model_factory` is a callable (task, seed) -> ModelBackend. When
    omitted, the scripted demo model is used. Pass a factory returning
    an OllamaModel or CloudModel to run the same tasks with a real
    model (seeds are then recorded but do not change model behaviour).
    """
    tasks = load_tasks(tasks_path, fixtures_root)
    seeds = seeds if seeds is not None else [0, 1, 2]
    settings = settings if settings is not None else SETTINGS
    results_dir = Path(results_dir)
    runs_dir = results_dir / "runs"
    audit_dir = results_dir / "audit"
    runs_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    factory = model_factory or (lambda task, seed: default_model_factory(task, seed, fixtures_root))
    records: list[dict] = []
    for setting in settings:
        for task in tasks:
            for seed in seeds:
                model = factory(task, seed)
                if task["kind"] == "fix":
                    record = _run_fix_task(task, seed, setting, fixtures_root, audit_dir, model)
                else:
                    record = _run_review_task(task, seed, setting, fixtures_root, audit_dir, model)
                records.append(record)
                (runs_dir / f"{setting.name}-{task['id']}-seed{seed}.json").write_text(
                    json.dumps(record, indent=2), encoding="utf-8"
                )
    (runs_dir / "runs.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n", encoding="utf-8"
    )
    summary = summarize(records, seeds, model_note)
    (results_dir / "results.md").write_text(render_results(summary, records), encoding="utf-8")
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def summarize(records: list[dict], seeds: list[int], model_note: str) -> dict:
    n_seeds = len(seeds)
    settings = sorted({r["setting"] for r in records})
    by_setting: dict[str, dict] = {}
    for setting in settings:
        fix = [r for r in records if r["setting"] == setting and r["kind"] == "fix"]
        review = [r for r in records if r["setting"] == setting and r["kind"] == "review"]
        # pass@k over fix tasks (n seeds per task)
        passk: dict[str, float] = {}
        for k in (1, 2, 3):
            if k > n_seeds:
                continue
            vals = []
            for task_id in sorted({r["task"] for r in fix}):
                c = sum(1 for r in fix if r["task"] == task_id and r["passed"])
                vals.append(pass_at_k(n_seeds, c, k))
            passk[f"pass@{k}"] = round(sum(vals) / len(vals), 3) if vals else 0.0
        tokens = [r["tokens_in"] + r["tokens_out"] for r in fix if r["tokens_in"] is not None]
        lat = [r["latency_ms"] for r in fix if r["latency_ms"] is not None]
        costs = [r["cost_usd"] for r in fix if r["cost_usd"] is not None]
        cost_total = round(sum(costs), 4) if len(costs) == len(fix) else None
        tp = sum(r["review"]["true_positives"] for r in review)
        fp = sum(r["review"]["false_positives"] for r in review)
        known = sum(r["review"]["known_bugs"] for r in review)
        clean_fp = sum(
            r["review"]["false_positives"] for r in review if r["task"] == "review-03"
        )
        precision = round(tp / (tp + fp), 3) if (tp + fp) else None
        recall = round(tp / known, 3) if known else None
        fpr = round(fp / (tp + fp), 3) if (tp + fp) else None
        by_setting[setting] = {
            "pass@k": passk,
            "avg_tokens_per_fix_run": round(sum(tokens) / len(tokens), 1) if tokens else None,
            "avg_latency_ms_per_fix_run": round(sum(lat) / len(lat), 1) if lat else None,
            "cost_usd_total": cost_total,
            "review_precision": precision,
            "review_recall": recall,
            "review_false_positive_rate": fpr,
            "review_true_positives": tp,
            "review_false_positives": fp,
            "clean_fixture_false_positives": clean_fp,
            "fix_runs": len(fix),
            "review_runs": len(review),
        }
    return {"model": model_note, "seeds": seeds, "settings": by_setting}


def render_results(summary: dict, records: list[dict]) -> str:
    lines = [
        "# Eval results",
        "",
        f"Model: {summary['model']}",
        f"Seeds: {summary['seeds']}",
        "",
        "## Fix tasks — pass@k (3 fix tasks x 3 seeds each)",
        "",
        "| Setting | pass@1 | pass@2 | pass@3 | Avg tokens/run | Avg latency ms/run | Cost (USD) |",
        "|---|---|---|---|---|---|---|",
    ]
    for setting, s in summary["settings"].items():
        pk = s["pass@k"]
        cost = f"{s['cost_usd_total']:.4f}" if s["cost_usd_total"] is not None else "unknown"
        lines.append(
            f"| {setting} | {pk.get('pass@1', '-')} | {pk.get('pass@2', '-')} | {pk.get('pass@3', '-')} | "
            f"{s['avg_tokens_per_fix_run']} | {s['avg_latency_ms_per_fix_run']} | {cost} |"
        )
    lines += [
        "",
        "## Review quality — precision on injected bugs, false-positive rate",
        "",
        "| Setting | Precision | Recall | False-positive rate | True positives | False positives | Clean-fixture FPs |",
        "|---|---|---|---|---|---|---|",
    ]
    for setting, s in summary["settings"].items():
        lines.append(
            f"| {setting} | {s['review_precision']} | {s['review_recall']} | {s['review_false_positive_rate']} | "
            f"{s['review_true_positives']} | {s['review_false_positives']} | {s['clean_fixture_false_positives']} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- The demo model is scripted (seed 0 = correct, 1 = noisy, 2 = sloppy). These numbers measure the harness — budgets, checks, and ablations — not model capability. A real model (Ollama/cloud) runs the same tasks through the same runner.",
        "- pass@k uses the standard estimator 1 - C(n-c,k)/C(n,k) over n=3 seeds per task.",
        "- False-positive rate = false-positive findings / all findings, pooled across review runs. Clean-fixture FPs are findings on review-03, which has no injected bugs — any finding there is a false positive.",
        "- Cost is $0.00 for the demo model and for Ollama (both run locally, no provider). Cloud runs report cost from provider token counts and GOVERNED_AGENT_PRICE_PER_1K when set; otherwise cost is unknown, never invented.",
        "- Raw run logs: `runs/runs.jsonl` (one line per task run) and `runs/<setting>-<task>-seed<seed>.json`. Audit logs for each run are in `audit/`.",
        "",
    ]
    return "\n".join(lines)
