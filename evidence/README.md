# evidence/

The auditable record for the Phase 1 verification run (2026-11-10).
These are the files a stranger uses to check the milestone: clone the
repo, re-run, and compare.

## Files

- `verification-run-2026-11-10.jsonl` — the audit log of the
  verification review run (run `2dc271360ab8`): the reviewer on
  `demo-repo/` with the scripted demo model. 28 events, one run id.
  It records the model, every step, every tool call and result, and
  the outcome of all 5 checks on every step. The run found both
  injected bugs: `calculator.py:24` (`divide` uses `//`) and
  `calculator.py:31` (`average` divides by `len(values) + 1`), both
  confidence high.
- `verification-run-2026-11-10.manifest.json` — the run manifest:
  model, task hash, tools, checks, seed, budgets, versions, counts,
  outcome (`finished`).
- `eval-results-2026-11-10.md` — the published eval results table
  (demo model, 6 tasks x 3 seeds x 3 settings). Baseline: pass@1
  0.333, pass@2 0.667, pass@3 1.0; review precision 0.667, recall
  0.667, false-positive rate 0.333. The no-checks ablation drops
  review precision to 0.5 (fake citations get through); the
  low-budget ablation drops review recall to 0.444.
- `eval-summary-2026-11-10.json` — the same results as JSON.

## Reproduce

```bash
.venv/bin/python -m pytest -q            # 43 tests pass
.venv/bin/python scripts/run_reviewer.py  # reviewer on demo-repo/
.venv/bin/python scripts/run_evals.py     # regenerates the eval table
```

The demo model is scripted, so the reviewer and eval runs are
deterministic: same seed, same result. The full raw eval logs
(`evals/results/runs/`, `evals/results/audit/`) are regenerable and
not kept in the repo; the table and summary above are the published
record.

`evidence/runs/` is scratch for ad-hoc runs and is gitignored.
