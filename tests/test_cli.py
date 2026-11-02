"""`rmgr` commands against a copy of the sample bank: exit codes, output, and --json."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from resume_mgmt.cli import app
from resume_mgmt.render_pdf import SofficeNotFound
from resume_mgmt.resume_doc import load_content
from resume_mgmt.validate import validate

from test_sample_bank import APP, SAMPLE
from test_site import _fake_pdf
from test_validate import write


@pytest.fixture
def bank(tmp_path: Path) -> Path:
    root = tmp_path / "bank"
    shutil.copytree(SAMPLE, root)
    return root


def rmgr(*args, code: int = 0) -> str:
    result = CliRunner().invoke(app, [str(a) for a in args])
    assert result.exit_code == code, result.output
    return result.output


def _break(root: Path) -> None:
    write(root, "data/roles/broken.yaml", "")


def _no_soffice():
    raise SofficeNotFound("no soffice")


# --- validate / gaps ------------------------------------------------------------


def test_validate_reports_errors(bank: Path):
    _break(bank)
    out = rmgr("validate", "--root", bank, code=1)
    assert "error    data/roles/broken.yaml: file is empty" in out
    assert "FAILED: 1 errors" in out


def test_validate_strict_fails_on_warnings(bank: Path):
    (bank / "data/skills.yaml").unlink()
    assert rmgr("validate", "--root", bank).startswith("warning  data/skills.yaml")
    assert "FAILED: 0 errors, 1 warnings" in rmgr("validate", "--strict", "--root", bank, code=1)


def test_gaps_text_json_and_filters(bank: Path):
    assert "gaps shown" in rmgr("gaps", "--root", bank)
    full = json.loads(rmgr("gaps", "--json", "--limit", "0", "--root", bank))
    assert full["total"] == len(full["gaps"]) > 1
    kind = full["gaps"][0]["kind"]
    only = json.loads(rmgr("gaps", "--json", "--kind", kind, "--limit", "1", "--root", bank))
    assert len(only["gaps"]) == 1 and only["gaps"][0]["kind"] == kind
    assert set(only["gaps"][0]) == {"kind", "target", "detail", "priority"}


def test_gaps_refuses_invalid_bank(bank: Path):
    _break(bank)
    assert "run `rmgr validate` first" in rmgr("gaps", "--root", bank, code=1)


# --- extract --------------------------------------------------------------------


def test_extract(bank: Path):
    assert "new        resumes/2025-jane-doe-resume.txt" in rmgr("extract", "--root", bank).replace("sources/", "")
    (bank / "sources/resumes/bad.docx").write_text("not a zip", encoding="utf-8")
    out = rmgr("extract", "--root", bank, code=1)
    assert "error" in out and "bad.docx" in out
    assert "unchanged  sources/resumes/2025-jane-doe-resume.txt" in out


# --- applications ---------------------------------------------------------------


def test_new_application_and_stage(bank: Path):
    write(bank, "jobs/inbox/beta.md", "---\ncompany: Beta\ntitle: AI Security Engineer\n---\nbody")
    args = ("new", "application", bank / "jobs/inbox/beta.md", "--date", "2026-11-02", "--root", bank)
    assert "created applications/2026-11-02-beta-ai-security-engineer" in rmgr(*args)
    assert "exists" in rmgr(*args, code=1)

    folder = bank / "applications/2026-11-02-beta-ai-security-engineer"
    assert "Beta AI Security Engineer: applied" in rmgr("stage", folder, "applied", "--note", "x", "--date", "2026-11-03")
    rmgr("stage", folder, "ghosted", code=1)
    rmgr("stage", bank / "jobs", "applied", code=1)  # no status.yaml


def test_new_application_needs_company(bank: Path):
    write(bank, "jobs/inbox/raw.txt", "Detection Engineer\nWrite detections.")
    rmgr("new", "application", bank / "jobs/inbox/raw.txt", "--title", "X", "--root", bank, code=1)


def test_applications_log(bank: Path):
    out = rmgr("applications", "--root", bank)
    assert out.splitlines()[0].split() == ["COMPANY", "ROLE", "STAGE", "CREATED", "UPDATED"]
    assert "1 applications" in out
    [entry] = json.loads(rmgr("applications", "--json", "--root", bank))
    stage = entry["stage"]
    assert len(json.loads(rmgr("applications", "--json", "--stage", stage, "--root", bank))) == 1
    assert "no applications" in rmgr("applications", "--stage", "offer", "--root", bank)

    rmgr("stage", bank / APP, "rejected")
    assert "no applications" in rmgr("applications", "--active", "--root", bank)


def test_commands_refuse_invalid_bank(bank: Path):
    _break(bank)
    for args in (["applications"], ["inbox"], ["build", "site"], ["site-diff"]):
        out = rmgr(*args, "--root", bank, code=1)
        assert "error    data/roles/broken.yaml: file is empty" in out
        assert "bank has validation errors" in out


def test_inbox(bank: Path):
    write(bank, "jobs/inbox/new.md", "---\ncompany: Beta\ntitle: AI Security Engineer\n---\nbody")
    write(bank, "jobs/inbox/dup.md", "---\ncompany: Fabrikam\ntitle: Cloud Security Architect\n---\nbody")
    write(bank, "jobs/inbox/raw.md", "just pasted text")
    out = rmgr("inbox", "--root", bank)
    assert "new        jobs/inbox/new.md  Beta: AI Security Engineer" in out
    assert "duplicate  jobs/inbox/dup.md" in out
    assert "invalid    jobs/inbox/raw.md" in out
    assert "3 postings, 1 new" in out
    items = {i["path"]: i for i in json.loads(rmgr("inbox", "--json", "--root", bank))}
    assert items["jobs/inbox/new.md"]["company"] == "Beta"
    assert items["jobs/inbox/raw.md"]["error"]


# --- build / ats-check ----------------------------------------------------------


def test_build_resume_without_libreoffice_still_writes_the_rest(bank: Path, monkeypatch):
    import resume_mgmt.render_pdf as render_pdf

    monkeypatch.setattr(render_pdf, "require_soffice", _no_soffice)
    out = rmgr("build", "resume", bank / APP, "--root", bank)
    assert "no soffice" in out
    assert [line.rsplit("/", 1)[-1] for line in out.splitlines() if line.startswith("wrote")] == [
        "Jane-Doe-Resume.docx", "Jane-Doe-Resume.md", "Jane-Doe-Resume.txt"]


def test_ats_check(bank: Path):
    assert "run `rmgr build resume` first" in rmgr("ats-check", bank / APP, "--root", bank, code=1)
    rmgr("build", "resume", bank / APP, "--root", bank, "--no-pdf")

    report = json.loads(rmgr("ats-check", bank / APP, "--json", "--root", bank, code=1))
    assert not report["ok"]  # no PDF to count pages
    assert {c["name"] for c in report["checks"] if not c["ok"]} == {"page count"}
    assert 0 < report["coverage"] <= 1

    content = load_content(validate(bank), bank / APP)
    _fake_pdf(content.lines(), bank / APP / "Jane-Doe-Resume.pdf")
    out = rmgr("ats-check", bank / APP, "--root", bank)
    assert "FAIL" not in out and "keywords " in out
    rmgr("ats-check", bank / APP, "--min-coverage", "1.01", "--root", bank, code=1)


def test_build_site_errors(bank: Path, monkeypatch):
    import resume_mgmt.site as site

    write(bank, "notasite/keep.txt", "important")
    assert "not empty" in rmgr("build", "site", "--out", bank / "notasite", "--no-pdf", "--root", bank, code=1)

    monkeypatch.setattr(site, "require_soffice", _no_soffice)
    assert "Pass --no-pdf" in rmgr("build", "site", "--root", bank, code=1)

    profile = (bank / "data/profile.yaml").read_text(encoding="utf-8")
    write(bank, "data/profile.yaml", "\n".join(ln for ln in profile.splitlines() if not ln.startswith("site_url")))
    assert "set site_url" in rmgr("build", "site", "--no-pdf", "--root", bank, code=1)
    out = rmgr("build", "site", "--no-pdf", "--base-url", "https://example.test", "--root", bank)
    assert "leak guard passed" in out
    assert 'content="https://example.test/"' in (bank / "build/site/index.html").read_text(encoding="utf-8")


def test_build_site_leak_fails(bank: Path, monkeypatch):
    import resume_mgmt.site as site

    monkeypatch.setattr(site, "find_leaks", lambda bank_, text: ["profile.contact.email"])
    assert "profile.contact.email" in rmgr("build", "site", "--no-pdf", "--root", bank, code=1)
    assert not (bank / "build/site").exists()


# --- site-diff / leak-scan / schema ---------------------------------------------


def test_site_diff(bank: Path):
    assert "git archive" in rmgr("site-diff", "--base", "HEAD", "--root", bank, code=1)

    def git(*args):
        subprocess.run(["git", "-C", str(bank), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    assert "no public changes since HEAD" in rmgr("site-diff", "--base", "HEAD", "--root", bank)

    path = bank / "data/profile.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("Principal Security Architect", "Chief Architect", 1),
                    encoding="utf-8")
    out = rmgr("site-diff", "--base", "HEAD", "--root", bank)
    assert "changed  profile.headline\n         Chief Architect" in out


def test_leak_scan(bank: Path, tmp_path: Path):
    clean = tmp_path / "tool"
    write(clean, "README.md", "A resume tool.")
    assert "OK: nothing from the bank" in rmgr("leak-scan", clean, "--root", bank)
    write(clean, "notes.md", "Jane Doe was here")
    out = rmgr("leak-scan", clean, "--root", bank, code=1)
    assert "leak     notes.md: profile.name" in out
    assert "FAILED: 2 leaks" in out  # the full name and the name part 'Jane'


def test_schema_export(bank: Path):
    out = rmgr("schema", "--root", bank)
    assert (bank / "schemas/profile.schema.json").is_file()
    assert out.count("wrote ") == len(list((bank / "schemas").glob("*.schema.json")))
