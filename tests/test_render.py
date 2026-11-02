from datetime import date
from pathlib import Path

import pytest
import yaml
from docx import Document

from resume_mgmt.application import new_application, read_posting, slugify
from resume_mgmt.ats import check_structure, keyword_coverage, run_ats_check
from resume_mgmt.models import ApplicationStatus
from resume_mgmt.render_docx import render_docx
from resume_mgmt.render_pdf import find_soffice, render_pdf
from resume_mgmt.render_text import to_markdown, to_text
from resume_mgmt.resume_doc import fmt_period, load_content
from resume_mgmt.validate import validate

from test_validate import ROLE, accomplishment, write

APP = "applications/2026-11-01-acme-architect"

POSTING = """---
company: Acme
title: Cloud Security Architect
keywords: [Terraform]
---

# Cloud Security Architect

- Own cloud security posture management across AWS.
- Threat modeling for new services.
"""


@pytest.fixture
def bank(tmp_path: Path) -> Path:
    write(tmp_path, "sources/resumes/2023-resume.txt", "resume text")
    write(tmp_path, "data/profile.yaml", {
        "name": "Test Person",
        "headline": "Security Architect",
        "contact": {"email": "test@example.com", "phone": "555-0100", "location": "Denver, CO"},
        "links": [{"label": "GitHub", "url": "https://github.com/test"}],
    })
    write(tmp_path, "data/skills.yaml", {"categories": [
        {"name": "Cloud Security", "skills": [
            {"name": "CSPM", "aliases": ["cloud security posture management"]}, {"name": "AWS"}]},
        {"name": "Security Architecture", "skills": [{"name": "Threat Modeling"}]},
    ]})
    write(tmp_path, "data/certifications.yaml", {"certifications": [
        {"id": "cissp", "name": "CISSP", "issuer": "ISC2", "earned": "2021-09"}]})
    write(tmp_path, "data/education.yaml", {"education": [
        {"institution": "State U", "degree": "BS", "field": "Computer Science", "period": {"start": "2010-09", "end": "2014-05"}}]})
    write(tmp_path, "data/roles/acme-architect.yaml", ROLE)
    write(tmp_path, "data/roles/beta-engineer.yaml", {
        "id": "beta-engineer", "employer": "Beta", "title": "Security Engineer", "location": "Remote",
        "period": {"start": "2023-07", "end": "present"},
    })
    write(tmp_path, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment())
    write(tmp_path, f"{APP}/posting.md", POSTING)
    write(tmp_path, f"{APP}/status.yaml", {"company": "Acme", "title": "Cloud Security Architect", "created": "2026-11-01"})
    write(tmp_path, f"{APP}/resume.yaml", {
        "posting": "posting.md",
        "summary": "Security architect focused on AWS posture management.",
        "skills": ["CSPM", "AWS", "Threat Modeling"],
        "roles": [
            {"role_id": "acme-architect", "bullets": [
                {"text": "Rolled out CSPM across 4,200 AWS accounts", "sources": ["cspm-rollout"]}]},
            {"role_id": "beta-engineer", "condensed": True},
        ],
        "certifications": ["cissp"],
    })
    return tmp_path


def content(root: Path):
    b = validate(root)
    assert b.errors == [], b.errors
    return load_content(b, root / APP), b


def test_fmt_period():
    from resume_mgmt.models import Period

    assert fmt_period(Period(start="2021-03", end="2023-11")) == "Mar 2021 – Nov 2023"
    assert fmt_period(Period(start="2024-04", end="present")) == "Apr 2024 – Present"


def test_content_order_and_condensed_roles(bank: Path):
    c, _ = content(bank)
    assert [r.title for r in c.experience] == ["Security Engineer", "Security Architect"]  # newest first
    assert c.experience[0].bullets == []
    assert c.experience[1].meta_line == "Acme | Jan 2020 – Jun 2023"
    assert c.contact_line == "Denver, CO | test@example.com | 555-0100 | github.com/test"
    assert [g.line for g in c.skills] == ["Cloud Security: CSPM, AWS", "Security Architecture: Threat Modeling"]
    assert c.certifications == ["CISSP, ISC2, Sep 2021"]
    assert c.education == ["BS, Computer Science | State U | 2014"]
    assert c.sections() == ["Summary", "Experience", "Skills", "Certifications", "Education"]


def test_docx_passes_ats_checks(bank: Path, tmp_path: Path):
    c, b = content(bank)
    docx = render_docx(c, tmp_path / "out.docx")
    posting = read_posting(bank / APP / "posting.md")
    report = run_ats_check(c, docx, None, posting.body, b.skills, posting.meta.keywords)
    checks = {ch.name: ch for ch in report.checks}
    for name in ("layout", "header/footer empty", "docx text round-trip", "docx section order"):
        assert checks[name].ok, checks[name]
    assert not checks["page count"].ok  # no PDF given
    doc = Document(str(docx))
    assert all(not p.text for s in doc.sections for p in s.header.paragraphs)
    assert any(p.style.name == "List Bullet" for p in doc.paragraphs)


def test_structure_check_flags_tables(tmp_path: Path):
    doc = Document()
    doc.add_table(rows=1, cols=2)
    doc.save(str(tmp_path / "t.docx"))
    layout = check_structure(tmp_path / "t.docx")[0]
    assert not layout.ok and "tables" in layout.detail


def test_text_round_trip_catches_lost_lines(bank: Path, tmp_path: Path):
    from resume_mgmt.ats import check_text

    c, _ = content(bank)
    assert not check_text("x", "Test Person\nSummary", c).ok


def test_keyword_coverage_uses_aliases_and_extras(bank: Path):
    c, b = content(bank)
    posting = read_posting(bank / APP / "posting.md")
    hits = {k.keyword: k for k in keyword_coverage(posting.body, "\n".join(c.lines()), b.skills, posting.meta.keywords)}
    assert hits["CSPM"].posting_terms == ["cloud security posture management"]
    assert hits["CSPM"].covered
    assert hits["Threat Modeling"].covered  # in the skills section
    assert not hits["Terraform"].covered  # extra keyword with no evidence
    assert set(hits) == {"CSPM", "AWS", "Threat Modeling", "Terraform"}


def test_markdown_and_text(bank: Path):
    c, _ = content(bank)
    md, txt = to_markdown(c), to_text(c)
    assert md.startswith("# Test Person\n")
    assert "## Experience" in md and "- Rolled out CSPM across 4,200 AWS accounts" in md
    assert "EXPERIENCE" in txt and "Beta | Remote | Jul 2023 – Present" in txt
    for line in c.lines():
        assert line in txt or line.upper() in txt


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice not installed")
def test_pdf_round_trip(bank: Path, tmp_path: Path):
    c, b = content(bank)
    docx = render_docx(c, tmp_path / "out.docx")
    pdf = render_pdf(docx, tmp_path / "out.pdf")
    report = run_ats_check(c, docx, pdf)
    assert report.ok, [ch for ch in report.checks if not ch.ok]
    assert report.pages == 1


def test_slugify():
    assert slugify("Security Engineer - Detections Engineering & Automation") == (
        "security-engineer-detections-engineering-automation"
    )


def test_new_application_from_markdown(bank: Path):
    src = bank / "jobs/inbox/acme.md"
    write(bank, "jobs/inbox/acme.md", POSTING)
    folder = new_application(bank, src, url="https://acme.example/jobs/1", on=date(2026, 11, 2), role_slug="csa")
    assert folder.name == "2026-11-02-acme-csa"
    posting = read_posting(folder / "posting.md")
    assert posting.meta.company == "Acme" and posting.meta.url == "https://acme.example/jobs/1"
    assert posting.meta.source == "jobs/inbox/acme.md"
    assert "- Threat modeling for new services." in posting.body
    status = ApplicationStatus.model_validate(yaml.safe_load((folder / "status.yaml").read_text(encoding="utf-8")))
    assert status.stage == "drafted" and status.history[0].stage == "drafted"
    with pytest.raises(FileExistsError):
        new_application(bank, src, on=date(2026, 11, 2), role_slug="csa")
    assert validate(bank).errors == []


def test_new_application_from_docx_needs_company(bank: Path):
    doc = Document()
    doc.add_heading("Detection Engineer", level=1)
    doc.add_paragraph("Write detections.", style="List Bullet")
    path = bank / "jobs/inbox/beta.docx"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    with pytest.raises(Exception, match="company"):
        new_application(bank, path, title="Detection Engineer")
    folder = new_application(bank, path, company="Beta Corp", title="Detection Engineer", on=date(2026, 11, 2))
    assert folder.name == "2026-11-02-beta-corp-detection-engineer"
    body = read_posting(folder / "posting.md").body
    assert "# Detection Engineer" in body and "- Write detections." in body


def test_long_bullet_warns_and_bad_folder_errors(bank: Path):
    data = yaml.safe_load((bank / APP / "resume.yaml").read_text(encoding="utf-8"))
    data["roles"][0]["bullets"][0]["text"] = " ".join(["word"] * 26)
    write(bank, f"{APP}/resume.yaml", data)
    write(bank, "applications/acme/posting.md", "x")
    b = validate(bank)
    assert any("runs 26 words" in w.message for w in b.warnings)
    assert any("YYYY-MM-DD" in e.message for e in b.errors)


def test_invalid_status_is_error(bank: Path):
    write(bank, f"{APP}/status.yaml", {"company": "Acme", "title": "X", "created": "2026-11-01", "stage": "ghosted"})
    assert any("stage" in e.message for e in validate(bank).errors)


def test_application_log_and_stage(bank: Path):
    from resume_mgmt.application import application_log, set_stage

    folder = bank / APP
    status = set_stage(folder, "applied", "via careers page", on=date(2026, 11, 3))
    assert status.stage == "applied" and status.history[-1].note == "via careers page"
    b = validate(bank)
    assert b.errors == [] and not [w for w in b.warnings if "history" in w.message]
    [entry] = application_log(b.statuses)
    assert entry.to_dict()["stage"] == "applied" and entry.updated == date(2026, 11, 3)
    with pytest.raises(Exception, match="stage"):
        set_stage(folder, "ghosted")


def test_stage_out_of_sync_warns(bank: Path):
    write(bank, f"{APP}/status.yaml", {
        "company": "Acme", "title": "X", "created": "2026-11-01", "stage": "applied",
        "history": [{"date": "2026-11-01", "stage": "drafted"}],
    })
    assert any("last history entry" in w.message for w in validate(bank).warnings)


def test_inbox_flags_duplicates_and_invalid(bank: Path):
    from resume_mgmt.application import normalize_url, read_inbox

    write(bank, f"{APP}/status.yaml", {
        "company": "Acme", "title": "Cloud Security Architect", "created": "2026-11-01",
        "url": "https://www.acme.example/jobs/1/?utm=x",
    })
    write(bank, "jobs/inbox/same-url.md", "---\ncompany: Acme Inc\ntitle: Architect\nurl: http://acme.example/jobs/1\n---\nbody")
    write(bank, "jobs/inbox/same-title.md", "---\ncompany: ACME\ntitle: Cloud Security Architect\n---\nbody")
    write(bank, "jobs/inbox/new.md", "---\ncompany: Beta\ntitle: AI Security Engineer\n---\nbody")
    write(bank, "jobs/inbox/bad.md", "---\ntitle: No Company\n---\nbody")
    write(bank, "jobs/inbox/raw.md", "just pasted text")
    b = validate(bank)
    items = {i.path.removeprefix("jobs/inbox/"): i for i in read_inbox(b.root, b.statuses)}
    assert items["same-url.md"].duplicate_of == APP
    assert items["same-title.md"].duplicate_of == APP
    assert items["new.md"].duplicate_of is None and items["new.md"].error is None
    assert "company" in items["bad.md"].error and "frontmatter" in items["raw.md"].error
    assert {w.path for w in b.warnings} >= {"jobs/inbox/bad.md", "jobs/inbox/raw.md"}
    assert normalize_url("https://www.Acme.example/jobs/1/#apply") == "acme.example/jobs/1"


def test_structure_check_flags_text_boxes_graphics_and_columns(tmp_path: Path):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document()
    pict = OxmlElement("w:pict")
    pict.append(OxmlElement("w:txbxContent"))
    doc.add_paragraph().add_run()._r.append(pict)
    cols = OxmlElement("w:cols")
    cols.set(qn("w:num"), "2")
    doc.sections[0]._sectPr.append(cols)
    doc.sections[0].footer.paragraphs[0].text = "Page 1"
    doc.save(str(tmp_path / "t.docx"))
    layout, hf = check_structure(tmp_path / "t.docx")
    assert layout.detail == "found text boxes, graphics, multiple columns"
    assert not hf.ok and hf.detail == "Page 1"


def test_section_order_checks(bank: Path):
    from resume_mgmt.ats import check_sections

    c, _ = content(bank)
    text = "\n".join(c.lines())
    assert check_sections("x", text, c).ok
    assert check_sections("x", text.replace("\nSkills\n", "\nSkills:\n"), c).detail == (
        "heading 'Skills' not found on its own line")
    moved = text.replace("\nSummary\n", "\n") + "\nSummary"
    assert not check_sections("x", moved, c).ok


def test_report_coverage_and_json(bank: Path, tmp_path: Path):
    c, b = content(bank)
    docx = render_docx(c, tmp_path / "out.docx")
    report = run_ats_check(c, docx, None)
    assert report.keywords == [] and report.coverage is None
    report = run_ats_check(c, docx, None, read_posting(bank / APP / "posting.md").body, b.skills, ["Terraform"])
    data = report.to_dict()
    assert data["coverage"] == pytest.approx(3 / 4)
    assert data["ok"] is False and data["pages"] is None
    assert {"keyword": "Terraform", "covered": False, "posting_terms": ["Terraform"], "resume_terms": []} in data["keywords"]


def test_load_content_errors(bank: Path):
    b = validate(bank)
    with pytest.raises(ValueError, match="resume.yaml not found"):
        load_content(b, bank / "applications")
    b.profile = None
    with pytest.raises(ValueError, match="profile.yaml is missing"):
        load_content(b, bank / APP)


def test_new_application_from_text_and_plain_docx(bank: Path):
    write(bank, "jobs/inbox/raw.txt", "Detection Engineer\n\nWrite detections.\n")
    folder = new_application(bank, bank / "jobs/inbox/raw.txt", company="Beta", title="Detection Engineer",
                             on=date(2026, 11, 2))
    assert "Write detections." in read_posting(folder / "posting.md").body

    doc = Document()
    doc.add_paragraph("About the team.")
    doc.add_paragraph("")
    doc.save(str(bank / "jobs/inbox/plain.docx"))
    folder = new_application(bank, bank / "jobs/inbox/plain.docx", company="Gamma", title="Engineer",
                             on=date(2026, 11, 2))
    assert read_posting(folder / "posting.md").body.strip() == "About the team."


# --- LibreOffice discovery ------------------------------------------------------


def test_find_soffice_order(tmp_path: Path, monkeypatch):
    import resume_mgmt.render_pdf as rp

    exe = tmp_path / "soffice.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("RMGR_SOFFICE", str(exe))
    assert rp.find_soffice() == str(exe)
    monkeypatch.setenv("RMGR_SOFFICE", str(tmp_path / "missing.exe"))
    assert rp.find_soffice() is None  # an explicit but wrong path is not silently ignored
    with pytest.raises(rp.SofficeNotFound, match="RMGR_SOFFICE"):
        rp.require_soffice()

    monkeypatch.delenv("RMGR_SOFFICE")
    monkeypatch.setattr(rp.shutil, "which", lambda name: f"/opt/{name}" if name == "libreoffice" else None)
    assert rp.find_soffice() == "/opt/libreoffice"
    monkeypatch.setattr(rp.shutil, "which", lambda name: None)
    monkeypatch.setattr(rp, "CANDIDATES", [str(tmp_path / "nope"), str(exe)])
    assert rp.find_soffice() == str(exe)


def test_render_pdf_reports_failed_conversion(tmp_path: Path, monkeypatch):
    import sys

    monkeypatch.setenv("RMGR_SOFFICE", sys.executable)  # exits with an error and writes no PDF
    docx = tmp_path / "r.docx"
    Document().save(str(docx))
    with pytest.raises(RuntimeError, match="did not produce a PDF"):
        render_pdf(docx, tmp_path / "r.pdf", timeout=60)
    assert not (tmp_path / "r.pdf").exists()
