#!/usr/bin/env python3
"""Run an evidence-first review of a repo.

Usage:
    python scripts/run_reviewer.py [--repo PATH] [--model demo|ollama|cloud]
                                   [--ollama-model NAME] [--out PATH] [--audit-dir PATH]

The demo model runs the full review offline with no keys and no GPU,
using a scripted walk of the demo repo: list, read, test, draft
findings for the injected bugs, done. With --model ollama the same
review runs against a local Ollama model; --model cloud uses the
environment API key (GOVERNED_AGENT_API_KEY).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from governed_agent.models import CloudModel, OllamaModel, ScriptedModel  # noqa: E402
from governed_agent.reviewer import review_repo  # noqa: E402

# Scripted demo walk of demo-repo/: list, read the module, run its
# tests, read the tests, draft the two injected-bug findings, done.
# Line numbers are the real ones in demo-repo/calculator.py
# (divide bug: line 24; average bug: line 31).
DEMO_SCRIPT = [
    '{"tool": "list_dir", "args": {"path": "."}}',
    '{"tool": "read_file", "args": {"path": "calculator.py"}}',
    '{"tool": "run_tests", "args": {"path": "."}}',
    '{"tool": "read_file", "args": {"path": "test_calculator.py"}}',
    '{"tool": "draft_finding", "args": {"title": "divide() uses integer division", "file": "calculator.py", "line": 24, "evidence": "return a // b", "confidence": "high", "severity": "high"}}',
    '{"tool": "draft_finding", "args": {"title": "average() divides by len(values) + 1", "file": "calculator.py", "line": 31, "evidence": "return sum(values) / (len(values) + 1)", "confidence": "high", "severity": "high"}}',
    '{"done": true, "result": "reviewed calculator.py; two defects demonstrated by failing tests"}',
]


def build_model(name: str, ollama_model: str):
    if name == "demo":
        return ScriptedModel(script=DEMO_SCRIPT)
    if name == "ollama":
        return OllamaModel(model=ollama_model)
    if name == "cloud":
        return CloudModel()
    raise SystemExit(f"unknown model backend: {name!r} (demo|ollama|cloud)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-first repo review.")
    parser.add_argument("--repo", default=str(ROOT / "demo-repo"), help="Repo to review.")
    parser.add_argument("--model", default="demo", choices=["demo", "ollama", "cloud"])
    parser.add_argument("--ollama-model", default="llama3.1:8b")
    parser.add_argument("--out", default=None, help="Write the Markdown report to this path.")
    parser.add_argument("--audit-dir", default=None, help="Directory for the audit log + manifest.")
    args = parser.parse_args(argv)

    model = build_model(args.model, args.ollama_model)
    report = review_repo(
        Path(args.repo),
        model,
        audit_dir=Path(args.audit_dir) if args.audit_dir else None,
    )
    print(report.to_markdown())
    print(f"Run: {report.run_id} · Status: {report.status}")
    print(f"Audit log: {report.audit_path}")
    print(f"Manifest: {report.manifest_path}")
    if args.out:
        out = Path(args.out)
        out.write_text(report.to_markdown(), encoding="utf-8")
        out.with_suffix(".json").write_text(report.to_json(), encoding="utf-8")
        print(f"Report written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
