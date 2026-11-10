"""Tests for the governed skills."""

from pathlib import Path

from governed_agent.skills import load_skill, load_skills_dir, validate_skill

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

EXPECTED_SKILL_NAMES = [
    "check-before-send",
    "evidence-first-review",
    "governed-read",
    "local-model-eval-run",
    "trace-and-manifest",
]


def test_all_five_skills_load_and_validate():
    skills = load_skills_dir(SKILLS_DIR)
    assert sorted(s.name for s in skills) == sorted(EXPECTED_SKILL_NAMES)
    for skill in skills:
        problems = validate_skill(skill)
        assert problems == [], f"{skill.name}: {problems}"


def test_skill_has_required_sections():
    for skill in load_skills_dir(SKILLS_DIR):
        assert skill.missing_sections() == []
        for section in ("trigger", "procedure", "resources", "checks", "security"):
            assert getattr(skill, section).strip(), f"{skill.name} missing {section}"
        assert len(skill.procedure.strip().splitlines()) >= 2


def test_bad_skill_fails_validation(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text("# Bad skill\n\nOnly a title, no sections.\n")
    skill = load_skill(bad)
    problems = validate_skill(skill)
    assert any("missing section: Trigger" in p for p in problems)
    assert any("missing section: Procedure" in p for p in problems)


def test_procedure_without_numbered_steps_is_flagged(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text(
        "# Bad skill\n\n"
        "## Trigger\nx\n\n## Procedure\nDo the thing.\n\n"
        "## Resources\nx\n\n## Checks\nx\n\n## Security\nThis skill cannot write.\n"
    )
    problems = validate_skill(load_skill(bad))
    assert any("numbered steps" in p for p in problems)


def test_security_without_a_limit_is_flagged(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text(
        "# Bad skill\n\n"
        "## Trigger\nx\n\n## Procedure\n1. Do the thing.\n\n"
        "## Resources\nx\n\n## Checks\nx\n\n## Security\nBe careful.\n"
    )
    problems = validate_skill(load_skill(bad))
    assert any("explicit limit" in p for p in problems)
