# evidence-first-review

## Trigger
Reviewing code, a PR, or a repo for defects — whenever a finding would be reported to a human.

## Procedure
1. Read the code and its tests before forming any claim.
2. Run the repo's test suite and record which tests fail, and where.
3. For each suspected defect, find the exact file and line that demonstrates it.
4. Grade confidence: high only if a failing test or a demonstrated contradiction proves it; medium if the code contradicts its contract but no test demonstrates it; low if it is a suspicion with a citation; cannot_verify if the evidence is missing.
5. Draft the finding with file, line, evidence text copied from the file, confidence, and severity. Never report a finding without a citation.
6. If a check rejects a finding (bad citation, evidence not in the file), fix the citation or drop the finding — never ship it anyway.

## Resources
- `read_file`, `list_dir`, `search`, `run_tests`, `draft_finding` tools (read-only).
- The repo under review and its test suite.

## Checks
- Every finding cites a file and line that exist in the repo.
- Every finding's evidence text appears verbatim in the cited file.
- Confidence is high only with a demonstrated failure.
- No finding is sent, published, or written into the repo — drafts only.

## Security
- This skill cannot write to the reviewed repo, send anything, or publish anything.
- It must not include secrets or credentials in findings; a finding that looks like it contains a secret fails the check and stops the run.
- It reads only files inside the repo root; it cannot read outside it.
