# Eval results

Model: scripted-demo-v1 (seeded behaviours: 0=correct, 1=noisy, 2=sloppy)
Seeds: [0, 1, 2]

## Fix tasks — pass@k (3 fix tasks x 3 seeds each)

| Setting | pass@1 | pass@2 | pass@3 | Avg tokens/run | Avg latency ms/run | Cost (USD) |
|---|---|---|---|---|---|---|
| baseline | 0.333 | 0.667 | 1.0 | 742.8 | 0.2 | 0.0000 |
| low_budget | 0.333 | 0.667 | 1.0 | 402.9 | 0.1 | 0.0000 |
| no_checks | 0.333 | 0.667 | 1.0 | 742.8 | 0.2 | 0.0000 |

## Review quality — precision on injected bugs, false-positive rate

| Setting | Precision | Recall | False-positive rate | True positives | False positives | Clean-fixture FPs |
|---|---|---|---|---|---|---|
| baseline | 0.667 | 0.667 | 0.333 | 6 | 3 | 1 |
| low_budget | 0.8 | 0.444 | 0.2 | 4 | 1 | 1 |
| no_checks | 0.5 | 0.667 | 0.5 | 6 | 6 | 2 |

## Notes

- The demo model is scripted (seed 0 = correct, 1 = noisy, 2 = sloppy). These numbers measure the harness — budgets, checks, and ablations — not model capability. A real model (Ollama/cloud) runs the same tasks through the same runner.
- pass@k uses the standard estimator 1 - C(n-c,k)/C(n,k) over n=3 seeds per task.
- False-positive rate = false-positive findings / all findings, pooled across review runs. Clean-fixture FPs are findings on review-03, which has no injected bugs — any finding there is a false positive.
- Cost is $0.00 for the demo model and for Ollama (both run locally, no provider). Cloud runs report cost from provider token counts and GOVERNED_AGENT_PRICE_PER_1K when set; otherwise cost is unknown, never invented.
- Raw run logs: `runs/runs.jsonl` (one line per task run) and `runs/<setting>-<task>-seed<seed>.json`. Audit logs for each run are in `audit/`.
