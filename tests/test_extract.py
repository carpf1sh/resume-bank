from pathlib import Path

from docx import Document

from resume_mgmt.extract import extract, extract_all, extract_docx

from test_site import _fake_pdf


def make_docx(path: Path) -> None:
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = "Header Name"
    doc.add_paragraph("Experience")
    doc.add_paragraph("Led SIEM migration", style="List Bullet")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Left cell"
    table.cell(0, 1).text = "Right cell"
    doc.add_paragraph("After table")
    doc.save(str(path))


def test_extract_docx_keeps_order_tables_and_bullets(tmp_path: Path):
    path = tmp_path / "r.docx"
    make_docx(path)
    lines = extract_docx(path).splitlines()
    assert lines == ["Header Name", "Experience", "- Led SIEM migration", "Left cell", "Right cell", "After table"]


def test_extract_all_writes_and_detects_unchanged(tmp_path: Path):
    (tmp_path / "sources" / "resumes").mkdir(parents=True)
    make_docx(tmp_path / "sources" / "resumes" / "a.docx")
    (tmp_path / "sources" / "resumes" / "~$a.docx").write_text("lock file")

    first = extract_all(tmp_path)
    assert [(s.name, status) for s, _, status in first] == [("a.docx", "new")]
    out = tmp_path / "sources" / "extracted" / "resumes" / "a.docx.txt"
    assert out.read_text(encoding="utf-8").startswith("# source: sources/resumes/a.docx\n")

    second = extract_all(tmp_path)
    assert [status for _, _, status in second] == ["unchanged"]


def test_extract_docx_merged_and_nested_tables(tmp_path: Path):
    doc = Document()
    doc.add_paragraph("")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).merge(table.cell(0, 1)).text = "Merged"
    table.cell(1, 0).text = "Outer"
    table.cell(1, 1).add_table(rows=1, cols=1).cell(0, 0).text = "Inner"
    doc.save(str(tmp_path / "t.docx"))
    assert extract_docx(tmp_path / "t.docx").splitlines() == ["Merged", "Outer", "Inner"]


def test_extract_pdf_csv_and_text(tmp_path: Path):
    _fake_pdf(["Jane Doe", "Security Architect"], tmp_path / "r.pdf")
    assert extract(tmp_path / "r.pdf").split() == ["Jane", "Doe", "Security", "Architect"]

    (tmp_path / "Positions.csv").write_text(
        "﻿Company Name,Title,Description\nAcme,Architect,\nBeta,Engineer,Detections\n", encoding="utf-8")
    assert extract(tmp_path / "Positions.csv") == (
        "Company Name: Acme\nTitle: Architect\n\nCompany Name: Beta\nTitle: Engineer\nDescription: Detections\n")

    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")
    assert extract(tmp_path / "notes.md") == "# Notes\n"


def test_extract_all_reports_errors_and_updates(tmp_path: Path):
    src = tmp_path / "sources" / "resumes"
    src.mkdir(parents=True)
    (src / "bad.docx").write_text("not a zip", encoding="utf-8")
    (src / "a.txt").write_text("v1", encoding="utf-8")
    (src / "skip.png").write_bytes(b"\x89PNG")
    results = {s.name: status for s, _, status in extract_all(tmp_path)}
    assert results["a.txt"] == "new" and results["bad.docx"].startswith("error: ")
    assert "skip.png" not in results

    (src / "a.txt").write_text("v2", encoding="utf-8")
    assert {s.name: status for s, _, status in extract_all(tmp_path)}["a.txt"] == "updated"
    assert {s.name: status for s, _, status in extract_all(tmp_path, force=True)}["a.txt"] == "updated"
    extracted = tmp_path / "sources" / "extracted"
    # extracted/ itself is never re-extracted
    assert [p.relative_to(extracted).as_posix() for p in extracted.rglob("*.txt")] == ["resumes/a.txt.txt"]
