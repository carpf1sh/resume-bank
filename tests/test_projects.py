"""Projects, from loading through validation, the site, the leak guard, site-diff, and tailored resumes."""

import subprocess
from pathlib import Path

import pytest

from resume_mgmt.resume_doc import load_content
from resume_mgmt.site import find_leaks
from resume_mgmt.site_diff import public_diff
from resume_mgmt.validate import validate

from test_site import _build, bank  # noqa: F401  (fixture)
from test_validate import write

PUBLIC_DESC = "Open-source threat modeling templates for cloud services"
PRIVATE_DESC = "Internal scanner that crawls every Acme production subnet nightly"
APP = "applications/2026-11-01-acme-architect"


def project(**overrides):
    proj = {
        "id": "threat-model-kit",
        "name": "Threat Model Kit",
        "url": "https://github.com/test/threat-model-kit",
        "period": {"start": "2022-01", "end": "2022-06"},
        "description": PUBLIC_DESC,
        "skills": ["CSPM"],
        "domains": ["cloud-security"],
        "sources": ["sources/resumes/2023-resume.txt"],
    }
    proj.update(overrides)
    return proj


@pytest.fixture
def projects(bank: Path) -> Path:
    write(bank, "data/projects/threat-model-kit.yaml", project())
    write(bank, "data/projects/acme-internal-scanner.yaml", project(
        id="acme-internal-scanner", name="Acme Internal Scanner", url=None, visibility="private",
        description=PRIVATE_DESC,
    ))
    assert validate(bank).errors == []
    return bank


def messages(root: Path) -> list[str]:
    return [i.message for i in validate(root).errors]


def test_projects_load(projects: Path):
    b = validate(projects)
    assert set(b.projects) == {"threat-model-kit", "acme-internal-scanner"}
    assert b.paths["threat-model-kit"] == "data/projects/threat-model-kit.yaml"


def test_public_project_needs_text(projects: Path):
    write(projects, "data/projects/threat-model-kit.yaml", project(description=""))
    assert "public project needs public_text or description" in messages(projects)


def test_project_sources_checked(projects: Path):
    write(projects, "data/projects/threat-model-kit.yaml", project(sources=["sources/missing.docx"]))
    assert any("source not found" in m for m in messages(projects))


def test_project_id_clashes_with_accomplishment(projects: Path):
    write(projects, "data/projects/dup.yaml", project(id="cspm-rollout"))
    assert any("duplicate id 'cspm-rollout'" in m for m in messages(projects))


def test_site_shows_public_projects_only(projects: Path):
    page = _build(projects)
    assert "Threat Model Kit" in page
    assert PUBLIC_DESC in page
    assert "Acme Internal Scanner" not in page
    assert "acme-internal-scanner" not in page
    assert "crawls every Acme production subnet" not in page


def test_project_public_text_wins_over_description(projects: Path):
    write(projects, "data/projects/threat-model-kit.yaml", project(public_text="Threat modeling templates, MIT licensed"))
    page = _build(projects)
    assert "Threat modeling templates, MIT licensed" in page
    assert PUBLIC_DESC not in page


@pytest.mark.parametrize("text, leak", [
    (PRIVATE_DESC, "non-public project 'acme-internal-scanner' text"),
    ("see acme-internal-scanner", "non-public id 'acme-internal-scanner'"),
])
def test_find_leaks_private_project(projects: Path, text: str, leak: str):
    assert leak in find_leaks(validate(projects), f"<p>{text}</p>")


def test_find_leaks_private_project_public_text(projects: Path):
    write(projects, "data/projects/acme-internal-scanner.yaml", project(
        id="acme-internal-scanner", visibility="resume", public_text="A nightly network scanner for production subnets"))
    leaks = find_leaks(validate(projects), "<p>A nightly network scanner for production subnets</p>")
    assert "non-public project 'acme-internal-scanner' text" in leaks


def _commit(root: Path) -> None:
    def git(*args):
        subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")


def test_site_diff_tracks_projects(projects: Path):
    _commit(projects)
    write(projects, "data/projects/acme-internal-scanner.yaml", project(
        id="acme-internal-scanner", name="Scanner", description="A nightly network scanner"))
    write(projects, "data/projects/threat-model-kit.yaml", project(public_text="Threat modeling templates"))
    changes = {(c.kind, c.what, c.text) for c in public_diff(validate(projects), "HEAD")}
    assert changes == {
        ("added", "project acme-internal-scanner", "A nightly network scanner"),
        ("changed", "project threat-model-kit", "Threat modeling templates"),
    }


def _tailored(root: Path, projects: list[str]) -> None:
    write(root, f"{APP}/posting.md", "posting")
    write(root, f"{APP}/resume.yaml", {
        "posting": "posting.md",
        "summary": "Security architect.",
        "roles": [{"role_id": "acme-architect", "bullets": [{"text": "Rolled out CSPM", "sources": ["cspm-rollout"]}]}],
        "projects": projects,
    })


def test_tailored_resume_lists_projects_last(projects: Path):
    _tailored(projects, ["threat-model-kit"])
    b = validate(projects)
    assert b.errors == []
    c = load_content(b, projects / APP)
    assert c.projects == [f"Threat Model Kit: {PUBLIC_DESC}"]
    assert c.sections()[-1] == "Projects"
    assert c.lines()[-2:] == ["Projects", f"Threat Model Kit: {PUBLIC_DESC}"]


@pytest.mark.parametrize("pid, error", [
    ("nope", "unknown project 'nope'"),
    ("acme-internal-scanner", "private project 'acme-internal-scanner'"),
])
def test_tailored_resume_rejects_bad_projects(projects: Path, pid: str, error: str):
    _tailored(projects, [pid])
    assert error in messages(projects)
