from pathlib import Path

from docx import Document

from resume_mgmt.extract import extract_all, extract_docx


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
