#!/usr/bin/env python3
"""Run the Phase 1 eval suite.

Usage:
    python scripts/run_evals.py [--model demo|ollama|cloud]
                                [--ollama-model NAME]
                                [--out DIR] [--seeds 0,1,2] [--settings baseline,low_budget,no_checks]

The demo model is scripted and runs offline with no keys and no GPU.
It measures the harness (budgets, checks, ablations), not model
capability. --model ollama runs the same tasks against a local Ollama
model; --model cloud uses the environment API key
(GOVERNED_AGENT_API_KEY). Results land in <out>/results.md plus raw
logs in <out>/runs/ and audit logs in <out>/audit/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from governed_agent.evals import SETTINGS, run_suite  # noqa: E402
from governed_agent.models import CloudModel, OllamaModel  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the governed-agent eval suite.")
    parser.add_argument("--model", default="demo", choices=["demo", "ollama", "cloud"])
    parser.add_argument("--ollama-model", default="llama3.1:8b")
    parser.add_argument("--out", default=str(ROOT / "evals" / "results"))
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument(
        "--settings", default="baseline,low_budget,no_checks",
        help="Comma-separated subset of: baseline, low_budget, no_checks.",
    )
    args = parser.parse_args(argv)

    seeds = [int(s) for s in args.seeds.split(",") if s.strip() != ""]
    wanted = {s.strip() for s in args.settings.split(",")}
    settings = [s for s in SETTINGS if s.name in wanted]
    if not settings:
        raise SystemExit(f"no known settings in {args.settings!r}")

    factory = None
    note = "scripted-demo-v1 (seeded behaviours: 0=correct, 1=noisy, 2=sloppy)"
    if args.model == "ollama":
        model = OllamaModel(model=args.ollama_model)
        factory = lambda task, seed: model
        note = f"ollama:{args.ollama_model} (seeds recorded; model is not seeded)"
    elif args.model == "cloud":
        model = CloudModel()
        factory = lambda task, seed: model
        note = f"cloud:{model.model} (seeds recorded; model is not seeded)"

    summary = run_suite(
        ROOT / "evals" / "tasks.json",
        ROOT / "evals" / "fixtures",
        Path(args.out),
        seeds=seeds,
        settings=settings,
        model_note=note,
        model_factory=factory,
    )
    print(json.dumps(summary, indent=2))
    print(f"Results table: {Path(args.out) / 'results.md'}")
    print(f"Raw logs: {Path(args.out) / 'runs' / 'runs.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
