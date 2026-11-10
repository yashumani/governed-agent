"""governed_agent — a deterministic, governed agent harness.

Phase 1 of the governed, evidence-first agent flagship: an agent loop
(task + context -> plan -> act -> observe -> check -> finish) with a tool
allowlist, read-only-by-default operation, human approval before any
irreversible action, step-level tracing, and a run manifest + audit log
for every run so any run is reproducible.

Standard library only. No API keys or GPU required to run the demo
model; Ollama (local) and one cloud model (environment API key) are
supported as backends.
"""

__version__ = "0.1.0"

from governed_agent.audit import AuditLog, RunManifest
from governed_agent.checks import Check, CheckResult
from governed_agent.harness import Agent, AgentConfig, AgentRun
from governed_agent.models import CloudModel, ModelBackend, OllamaModel, ScriptedModel
from governed_agent.reviewer import Finding, review_repo
from governed_agent.tools import Tool, ToolRegistry

__all__ = [
    "__version__",
    "Agent",
    "AgentConfig",
    "AgentRun",
    "AuditLog",
    "Check",
    "CheckResult",
    "CloudModel",
    "Finding",
    "ModelBackend",
    "OllamaModel",
    "RunManifest",
    "ScriptedModel",
    "Tool",
    "ToolRegistry",
    "review_repo",
]
