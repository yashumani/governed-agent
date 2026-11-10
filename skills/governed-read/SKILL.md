# governed-read

## Trigger
Exploring a repository — reading code, listing files, searching contents — before any other action.

## Procedure
1. List the repo root first; do not assume its layout.
2. Read files by path, one at a time; use search to locate a symbol or string instead of reading everything.
3. Stay inside the repo root. A path that escapes the root is rejected by the tool layer.
4. Do not run anything that writes, installs, or changes state while exploring.
5. Summarise what you found with file/line citations before proposing any change.

## Resources
- `read_file`, `list_dir`, `search` tools (read-only).

## Checks
- No tool call leaves the repo root.
- No mutating tool is called during exploration.
- Any claim about the code cites file and line.

## Security
- This skill cannot write, delete, execute arbitrary commands, or access files outside the repo root.
- It must not read files that look like credentials (.env, *.pem, id_rsa) — the tool layer refuses files over the size limit and the check layer refuses secrets in output.
