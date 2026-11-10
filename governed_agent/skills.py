"""Governed skills: loading and validation.

A skill is a SKILL.md file with a fixed shape:

    # <name>
    Trigger: ... (when the skill applies)
    Procedure: ... (numbered steps)
    Resources: ... (files/tools it may use)
    Checks: ... (what must hold before it reports done)
    Security: ... (what it can/cannot do, what data it touches)

`load_skill` parses that shape; `validate_skill` enforces it. A skill
that fails validation cannot be registered — an untested, unscoped
skill is not a governed skill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_SECTIONS = ("Trigger", "Procedure", "Resources", "Checks", "Security")


@dataclass
class Skill:
    name: str
    path: Path
    trigger: str = ""
    procedure: str = ""
    resources: str = ""
    checks: str = ""
    security: str = ""
    raw: str = ""

    def missing_sections(self) -> list[str]:
        return [s for s in REQUIRED_SECTIONS if not getattr(self, s.lower()).strip()]


_SECTION_RE = re.compile(r"^##\s+(Trigger|Procedure|Resources|Checks|Security)\s*$", re.MULTILINE)


def load_skill(path: Path) -> Skill:
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    title = ""
    first = raw.splitlines()[0] if raw.splitlines() else ""
    if first.startswith("# "):
        title = first[2:].strip()
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(raw))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[match.group(1)] = raw[start:end].strip()
    return Skill(
        name=title or path.parent.name,
        path=path,
        trigger=sections.get("Trigger", ""),
        procedure=sections.get("Procedure", ""),
        resources=sections.get("Resources", ""),
        checks=sections.get("Checks", ""),
        security=sections.get("Security", ""),
        raw=raw,
    )


def validate_skill(skill: Skill) -> list[str]:
    """Return a list of validation problems; empty means valid."""
    problems = []
    for section in skill.missing_sections():
        problems.append(f"missing section: {section}")
    if skill.procedure and not re.search(r"(?m)^\s*1[.)]\s", skill.procedure):
        problems.append("Procedure has no numbered steps")
    if skill.security and "cannot" not in skill.security.lower() and "must not" not in skill.security.lower():
        problems.append("Security note states no explicit limit (say what the skill cannot do)")
    return problems


def load_skills_dir(skills_dir: Path) -> list[Skill]:
    """Load every SKILL.md under `skills_dir` (one folder per skill)."""
    skills = []
    for path in sorted(Path(skills_dir).glob("*/SKILL.md")):
        skills.append(load_skill(path))
    return skills
