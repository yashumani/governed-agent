# Changelog

## v0.1.0 — 2026-11-10 (Phase 1 scaffold)

First public scaffold of the governed-agent harness (Project 1 v1 +
Project 2 v0 + the first 5 governed skills).

- Deterministic agent harness (`governed_agent/harness.py`):
  plan → act (one tool per step) → observe → check → finish/stop,
  with max steps and a model-call budget. Step-level tracing and a run
  manifest (model, prompt, tools, versions, seed) for every run.
- Model backends (`governed_agent/models.py`): Ollama (local, plain
  HTTP, no SDK), one cloud model via `GOVERNED_AGENT_API_KEY`, and a
  deterministic scripted demo model that runs the whole suite with no
  keys and no GPU.
- Tool allowlist, read-only by default (`governed_agent/tools.py`):
  human approval required before any write/send/delete/publish, plus a
  tool-layer write gate. Path confinement keeps tools inside the repo.
- Governed checks (`governed_agent/checks.py`): rules that can stop a
  run — citation required, evidence must match the file, allowlist
  enforcement, budget. Retryable failures retry; fatal failures stop.
- Audit log (`governed_agent/audit.py`): a JSONL log plus a run
  manifest written for every run.
- Evidence-first repo reviewer (`governed_agent/reviewer.py`): every
  finding cites file/line with a confidence grade; unverifiable claims
  are recorded as `cannot_verify`. Drafts findings only — it never
  sends, deletes, or publishes.
- Eval suite (`governed_agent/evals.py`, `evals/`): 6 held-out tasks
  (3 fix, 3 review) with task hashes and seeds, a harness-vs-model
  ablation (baseline / low step budget / checks disabled), pass@k,
  cost/latency/token reporting, a Markdown results table, and raw run
  logs. Review quality is graded as precision on injected bugs and
  false-positive rate.
- Skills (`skills/`): the first 5 governed skills, each with trigger,
  procedure, resources, checks, and security notes, plus tests.
- `demo-repo/`: a demo repo fixture with two injected bugs, so the
  reviewer runs end-to-end offline.
- CLI entry points: `scripts/run_reviewer.py`, `scripts/run_evals.py`.
- `evidence/`: the Phase 1 verification run's audit record (one JSONL
  file + its run manifest).

Verification for this release (run 2026-11-10, see `evidence/`):
- Full pytest suite: **43 tests pass** (`python -m pytest -q`).
- Reviewer on `demo-repo/` with the demo model (run `2dc271360ab8`,
  status `finished`): finds both injected bugs with file/line
  citations and high confidence — `calculator.py:24` (`divide` uses
  `//`) and `calculator.py:31` (`average` divides by `len(values) +
  1`) — and writes an audit log (28 events) plus run manifest.
- Eval suite with the demo model (6 tasks x 3 seeds x 3 settings):
  baseline pass@1 0.333, pass@2 0.667, pass@3 1.0; review precision
  0.667, recall 0.667, false-positive rate 0.333. Ablations: checks
  disabled drops review precision to 0.5 (fake citations get
  through); low step budget drops review recall to 0.444. Results
  table and raw logs produced; the published table is in `evidence/`.
