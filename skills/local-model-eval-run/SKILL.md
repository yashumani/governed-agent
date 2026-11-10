# local-model-eval-run

## Trigger
Running the eval suite to measure the harness or a model — whenever a number will be reported or compared.

## Procedure
1. Confirm the task set, task hashes, and seeds before running anything.
2. Run the eval suite with the named model backend and harness settings; record the settings in the run manifest.
3. Report pass@k, cost, latency, and tokens from the raw logs — never from memory.
4. Write the results table (Markdown) and keep the raw run logs next to it.
5. State the ablation plainly: same model, different harness settings, same tasks.
6. If a run cannot be reproduced from its manifest + logs, say so and do not publish the number.

## Resources
- `evals/tasks.json` (held-out tasks, hashes, seeds), `scripts/run_evals.py`, the demo model backend.
- The eval results directory for tables and raw logs.

## Checks
- Task hashes match the recorded hashes before the run starts.
- Every reported number traces to a raw log line.
- Cost is reported as 0 only for local/demo runs, with that fact stated; cloud cost uses the provider's token counts and a stated price.
- The results table lists the harness settings used.

## Security
- This skill cannot publish results anywhere; it writes only to the local results directory.
- It must not invent a score, a baseline, or a comparison. A missing baseline is reported as missing.
- It cannot run code outside the eval sandbox directories.
