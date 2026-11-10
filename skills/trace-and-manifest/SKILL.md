# trace-and-manifest

## Trigger
Every run of the harness, the reviewer, or the eval suite — no run without a record.

## Procedure
1. Before the run, record the run manifest: model, task hash, tools, checks, versions, seed, budgets.
2. During the run, append one audit-log line per event: model calls, tool calls, tool results, check outcomes, approvals.
3. After the run, record the outcome and the counts (steps, model calls, tokens, latency) in the manifest.
4. Store the manifest and the audit log together; a log without its manifest is incomplete.
5. To reproduce a run, re-run with the same manifest values and compare the audit logs.

## Resources
- The audit log (JSONL) and run manifest (JSON) written by the harness.
- The `evidence/` directory for the Phase 1 verification run's record.

## Checks
- A run with no audit log is a failed run, even if its output looks right.
- The manifest lists the model, the task hash, and the seed actually used.
- The audit log contains the model, tools, steps, check outcomes, and seed for the run.

## Security
- This skill cannot edit or delete audit records. The log is append-only.
- It must not record secrets in the log; the check layer refuses secret-shaped output.
- It cannot move a run's record out of the audit directory except into `evidence/` for a verified run.
