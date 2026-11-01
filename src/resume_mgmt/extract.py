"""Extract plain text from source documents into sources/extracted/.

The extracted text is what /ingest reads, and it is committed so that
re-analysis is reproducible and changes to sources show up as diffs.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

SUPPORTED = {".docx", ".pdf", ".csv", ".txt", ".md"}


def _docx_blocks(doc) -> Iterator[Paragraph | Table]:
    """Paragraphs and tables in document order (resumes often use layout tables)."""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


def _paragraph_text(p: Paragraph) -> str:
    text = p.text.strip()
    if not text:
        return ""
    style = (p.style.name or "").lower() if p.style is not None else ""
    is_list = "list" in style or p._p.pPr is not None and p._p.pPr.numPr is not None
    return f"- {text}" if is_list else text


def _table_lines(table: Table) -> Iterator[str]:
    seen: set[int] = set()
    for row in table.rows:
        for cell in row.cells:
            # Merged cells repeat the same underlying element.
            if id(cell._tc) in seen:
                continue
            seen.add(id(cell._tc))
            for p in cell.paragraphs:
                if line := _paragraph_text(p):
                    yield line
            for inner in cell.tables:
                yield from _table_lines(inner)


def extract_docx(path: Path) -> str:
    doc = Document(str(path))
    lines: list[str] = []
    for section in doc.sections:
        for p in section.header.paragraphs:
            if line := _paragraph_text(p):
                lines.append(line)
    for block in _docx_blocks(doc):
        if isinstance(block, Paragraph):
            lines.append(_paragraph_text(block))
        else:
            lines.extend(_table_lines(block))
    # Collapse runs of blank lines.
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip() + "\n"


def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p.strip() for p in pages).strip() + "\n"


def extract_csv(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    blocks = ["\n".join(f"{k}: {v}" for k, v in row.items() if v) for row in rows]
    return "\n\n".join(blocks).strip() + "\n"


def extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".csv":
        return extract_csv(path)
    return path.read_text(encoding="utf-8")


def extract_all(root: Path, force: bool = False) -> list[tuple[Path, Path, str]]:
    """Extract every supported file under sources/ (except sources/extracted).

    Returns (source, output, status) where status is 'new', 'updated', 'unchanged', or 'error: ...'.
    """
    sources = root / "sources"
    out_dir = sources / "extracted"
    results = []
    for src in sorted(sources.rglob("*")):
        if not src.is_file() or out_dir in src.parents or src.suffix.lower() not in SUPPORTED:
            continue
        if src.name.startswith("~$"):
            continue
        rel = src.relative_to(sources)
        out = out_dir / rel.parent / f"{src.name}.txt"
        try:
            text = extract(src)
        except Exception as e:  # corrupt or password-protected files shouldn't stop the run
            results.append((src, out, f"error: {e}"))
            continue
        header = f"# source: sources/{rel.as_posix()}\n\n"
        content = header + text
        if out.exists() and not force and out.read_text(encoding="utf-8") == content:
            results.append((src, out, "unchanged"))
            continue
        status = "updated" if out.exists() else "new"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8", newline="\n")
        results.append((src, out, status))
    return results
