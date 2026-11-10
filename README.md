# governed-agent

A governed, evidence-first agent harness that runs locally and can be
audited. Built as the Phase 1 scaffold of the EB-1A flagship project:
**governed, evidence-first agents that run locally and can be audited.**

The idea, in one sentence: an agent that plans, acts through a small
allowlisted tool set, and is checked by rules that can stop it — with a
complete audit trail for every run, so any result can be reproduced
and questioned.

## Governed principles

1. **Read-only by default.** The agent can read files, list
   directories, and run tests. Anything that writes, sends, deletes,
   or publishes needs a human's approval — and a second, separate
   write gate in the tool layer. No approval, no write. Ever.
2. **Checks can stop a run.** A check is a rule with teeth: a failed
   check retries the step (a citation that doesn't exist, evidence
   that doesn't match the file) or stops the run entirely (a tool
   outside the allowlist, a blown budget). A check that cannot stop
   the run is not a check.
3. **Every finding cites evidence.** The reviewer drafts findings
   only. Each finding must cite a file, a line, and the evidence text
   that appears there, with a confidence grade (high / medium / low).
   Anything that cannot be verified is recorded as `cannot_verify` —
   never invented.
4. **Every run is reproducible.** A run manifest records the model,
   prompt, tools, versions, and seed. A JSONL audit log records every
   step, observation, check outcome, and finding. Same seed, same
   tools, same result.
5. **Local first.** The default model is Ollama (plain HTTP, no SDK,
   no key). A cloud model is available via an environment API key for
   comparison only. A deterministic scripted demo model runs the whole
   suite with no keys and no GPU.

## Quickstart

```bash
git clone https://github.com/yashumani/governed-agent.git
cd governed-agent
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python scripts/run_reviewer.py
.venv/bin/python scripts/run_evals.py
.venv/bin/python -m pytest -q
```

### Run the reviewer on the demo repo

```bash
.venv/bin/python scripts/run_reviewer.py
```

Reviews `demo-repo/` (a small calculator module with two injected
bugs) with the demo model and prints the findings, each with a
file/line citation and confidence grade, plus the audit log and run
manifest paths. The reviewer drafts findings only — it never sends,
deletes, or publishes.

### Run the reviewer on your own repo (with Ollama)

```bash
ollama pull llama3.1:8b
.venv/bin/python scripts/run_reviewer.py --repo /path/to/your/repo --model ollama
```

### Run the evals

```bash
.venv/bin/python scripts/run_evals.py
```

Runs 6 held-out tasks (3 fix, 3 review) across 3 seeds and 3
harness settings (baseline, low step budget, checks disabled),
writing `evals/results/results.md` (results table), raw logs in
`evals/results/runs/`, and audit logs in `evals/results/audit/`.
The demo model is scripted — these evals measure the harness, not
model capability. `--model ollama` or `--model cloud` runs the same
tasks against a real model.

### Run the tests

```bash
.venv/bin/python -m pytest -q
```

## Layout

| Path | What it is |
|---|---|
| `governed_agent/` | The package: `harness.py` (plan→act→observe→check loop), `models.py` (Ollama / cloud / scripted demo), `tools.py` (allowlist, read-only tools, path confinement), `checks.py` (rules that can stop a run), `audit.py` (JSONL log + run manifest), `reviewer.py` (evidence-first findings), `evals.py` (held-out tasks, ablation, pass@k), `skills.py` (skill file loader/validator). |
| `scripts/run_reviewer.py` | CLI: review a repo. |
| `scripts/run_evals.py` | CLI: run the eval suite. |
| `skills/` | The first 5 governed skills: evidence-first-review, governed-read, local-model-eval-run, check-before-send, trace-and-manifest. Each is a file with trigger, procedure, resources, checks, and security notes. |
| `demo-repo/` | A demo repo fixture with two injected bugs (`calculator.py`: `divide` uses `//` at line 24, `average` divides by `len(values) + 1` at line 31), so the reviewer runs end-to-end offline. |
| `evals/` | The held-out task set (`tasks.json`, hash-verified), fixtures, and results. |
| `evidence/` | The Phase 1 verification run's audit record (one JSONL + its run manifest), the published eval results table + summary, and a README explaining how to reproduce both. Other run outputs are gitignored. |
| `tests/` | pytest tests for the harness, reviewer, checks, evals, and skills. |

## Phase 1 milestone

A stranger can clone this repo, run the reviewer on their own repo
with Ollama, and reproduce a published eval number from the logs in
`evidence/`. That is the bar Phase 1 is built to. The verification
run for this release is in `evidence/` — see `CHANGELOG.md`.

## Planning targets, not filing thresholds

Any adoption, star, or download figures mentioned in project planning
are planning targets only. They are never filing thresholds, and no
result in this repo is a claim that any immigration criterion is met.
This is a software project, not legal advice.
