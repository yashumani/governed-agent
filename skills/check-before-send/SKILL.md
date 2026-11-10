# check-before-send

## Trigger
Any step that would write a file, send a message, delete something, or publish anything.

## Procedure
1. Name the action, its target, and its effect before doing it.
2. Ask for human approval. Do not proceed without it.
3. If approval is denied, stop that action and record the denial in the audit log.
4. If approval is granted, do exactly the approved action — nothing wider.
5. After the action, record what changed in the audit log.

## Resources
- The harness approval gate (approval callback) and the audit log.

## Checks
- No mutating tool runs without a recorded approval.
- The approved scope matches the action taken (same tool, same target).
- Every approval request and decision is in the audit log.

## Security
- This skill cannot approve its own actions. Approval comes from a human (or, in evals, from a sandbox-scoped approver that only allows writes inside a temp directory).
- It must not bundle an approval for one action into a different, wider action.
- It cannot override a failed check.
