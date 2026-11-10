"""Tools for the governed harness: an allowlist, read-only by default.

Every tool a model may call is registered here, with a name, a
description, and whether it mutates anything. The harness only ever
exposes the tools on the run's allowlist, and any tool that writes
requires human approval before it runs — approval is enforced by the
harness, not requested politely by the model.

All file tools are confined to a repo root: paths are resolved and
rejected if they escape the root (no `..` traversal, no absolute
paths outside the root, no symlinks out of the root).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class ToolError(RuntimeError):
    """A tool call failed (bad args, missing file, path escape, ...)."""


@dataclass
class Tool:
    """One callable tool on the allowlist."""

    name: str
    description: str
    mutates: bool = False
    func: object = None  # callable(args: dict, ctx: ToolContext) -> dict


@dataclass
class ToolContext:
    """What a tool call runs against."""

    repo_root: Path
    allow_write: bool = False  # True only inside an approved sandbox


def _resolve(ctx: ToolContext, rel: str) -> Path:
    """Resolve `rel` inside the repo root, rejecting escapes."""
    if not rel or rel.startswith("/"):
        # Absolute paths are only allowed if they are inside the root.
        candidate = Path(rel) if rel.startswith("/") else ctx.repo_root / rel
    else:
        candidate = ctx.repo_root / rel
    try:
        resolved = candidate.resolve()
    except Exception as exc:  # pragma: no cover - pathological input
        raise ToolError(f"cannot resolve path {rel!r}: {exc}") from exc
    root = ctx.repo_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ToolError(f"path {rel!r} escapes the repo root")
    return resolved


def _read_file(args: dict, ctx: ToolContext) -> dict:
    path = _resolve(ctx, str(args.get("path", "")))
    if not path.is_file():
        raise ToolError(f"no such file: {args.get('path')!r}")
    if path.stat().st_size > 1_000_000:
        raise ToolError(f"file too large to read: {args.get('path')!r}")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start = int(args.get("start_line", 1)) - 1
    end = int(args.get("end_line", len(lines))) if args.get("end_line") else len(lines)
    return {
        "path": str(path.relative_to(ctx.repo_root.resolve())),
        "total_lines": len(lines),
        "lines": lines[max(0, start) : end],
        "start_line": max(0, start) + 1,
    }


def _list_dir(args: dict, ctx: ToolContext) -> dict:
    path = _resolve(ctx, str(args.get("path", ".")))
    if not path.is_dir():
        raise ToolError(f"no such directory: {args.get('path')!r}")
    entries = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
    return {"path": str(path.relative_to(ctx.repo_root.resolve())), "entries": entries}


def _search(args: dict, ctx: ToolContext) -> dict:
    needle = str(args.get("query", ""))
    if not needle:
        raise ToolError("search needs a query")
    hits: list[dict] = []
    root = ctx.repo_root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".md", ".txt", ".toml", ".json", ".js", ".ts"}:
            continue
        if ".venv" in path.parts or "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if needle in line:
                hits.append(
                    {
                        "file": str(path.relative_to(root)),
                        "line": i,
                        "text": line.strip()[:200],
                    }
                )
                if len(hits) >= 50:
                    return {"query": needle, "hits": hits, "truncated": True}
    return {"query": needle, "hits": hits, "truncated": False}


def _run_tests(args: dict, ctx: ToolContext) -> dict:
    """Run a test command inside the repo root and return its output.

    The command is fixed (pytest on a path inside the root, run with
    the same interpreter as the harness) — the model cannot supply an
    arbitrary shell command. Output is truncated.
    """
    import sys

    target = str(args.get("path", ""))
    path = _resolve(ctx, target) if target else ctx.repo_root
    cmd = [sys.executable, "-m", "pytest", "-q", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ctx.repo_root))
    out = (proc.stdout + proc.stderr)[-4000:]
    return {"command": " ".join(cmd), "returncode": proc.returncode, "output": out}


def _write_file(args: dict, ctx: ToolContext) -> dict:
    """Write a file. Mutating: the harness requires approval first."""
    if not ctx.allow_write:
        raise ToolError("write_file is not allowed in this run (read-only)")
    path = _resolve(ctx, str(args.get("path", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(args.get("content", "")), encoding="utf-8")
    return {"path": str(path.relative_to(ctx.repo_root.resolve())), "bytes": len(args.get("content", ""))}


def _draft_finding(args: dict, ctx: ToolContext) -> dict:
    """Record a draft finding. Drafts only — nothing is sent or published."""
    required = ("title", "file", "line", "evidence", "confidence")
    missing = [k for k in required if k not in args]
    if missing:
        raise ToolError(f"draft_finding missing fields: {missing}")
    if args["confidence"] not in ("high", "medium", "low", "cannot_verify"):
        raise ToolError(f"bad confidence grade: {args['confidence']!r}")
    return {
        "title": args["title"],
        "file": args["file"],
        "line": int(args["line"]),
        "evidence": str(args["evidence"])[:1000],
        "confidence": args["confidence"],
        "severity": args.get("severity", "medium"),
    }


# The default toolset: read-only tools plus the finding draft.
# write_file is registered but NOT on the default allowlist.
DEFAULT_TOOLS: list[Tool] = [
    Tool("read_file", "Read a file inside the repo (path, optional start_line/end_line).", False, _read_file),
    Tool("list_dir", "List a directory inside the repo (path).", False, _list_dir),
    Tool("search", "Search file contents for a string (query).", False, _search),
    Tool("run_tests", "Run pytest on a path inside the repo (path). Returns output.", False, _run_tests),
    Tool("draft_finding", "Draft a review finding (title, file, line, evidence, confidence, severity). Draft only.", False, _draft_finding),
    Tool("write_file", "Write a file inside the repo (path, content). MUTATING — needs human approval.", True, _write_file),
]

#: Tools on the allowlist for a normal review run (no writes).
READONLY_ALLOWLIST = ["read_file", "list_dir", "search", "run_tests", "draft_finding"]


class ToolRegistry:
    """The allowlist for one run: only these tools may be called."""

    def __init__(self, tools: list[Tool] | None = None, allowlist: list[str] | None = None):
        self._tools = {t.name: t for t in (tools if tools is not None else DEFAULT_TOOLS)}
        self.allowlist = list(allowlist if allowlist is not None else READONLY_ALLOWLIST)

    def describe(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "mutates": t.mutates}
            for t in self._tools.values()
            if t.name in self.allowlist
        ]

    def call(self, name: str, args: dict, ctx: ToolContext) -> dict:
        if name not in self.allowlist:
            raise ToolError(f"tool {name!r} is not on this run's allowlist")
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool {name!r}")
        return tool.func(args, ctx)  # type: ignore[operator]

    def is_mutating(self, name: str) -> bool:
        tool = self._tools.get(name)
        return bool(tool and tool.mutates)
