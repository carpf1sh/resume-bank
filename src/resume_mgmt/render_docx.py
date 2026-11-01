"""Render resume content to an ATS-safe .docx.

ATS rules (docs/build-plan.md, Phase 4): one column; no tables, text boxes,
columns, or graphics; contact details in the body, never the header/footer;
standard headings; Calibri 10.5pt; `MMM YYYY – MMM YYYY` dates; real bullets.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from .resume_doc import ResumeContent

FONT = "Calibri"
BODY_PT = 10.5
BLACK = RGBColor(0, 0, 0)


def _set_font(style, size: float, bold: bool | None = None) -> None:
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.color.rgb = BLACK
    if bold is not None:
        style.font.bold = bold
    # East Asian font slot, so Word doesn't substitute on some locales.
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), FONT)


def _bottom_border(paragraph) -> None:
    """A paragraph border (not a shape), so parsers still see plain text."""
    ppr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in {"w:val": "single", "w:sz": "6", "w:space": "1", "w:color": "000000"}.items():
        bottom.set(qn(k), v)
    borders.append(bottom)
    ppr.append(borders)


def _setup(doc) -> None:
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    for side in ("left_margin", "right_margin"):
        setattr(section, side, Inches(0.7))
    section.top_margin = section.bottom_margin = Inches(0.6)

    normal = doc.styles["Normal"]
    _set_font(normal, BODY_PT)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.0

    h1 = doc.styles["Heading 1"]
    _set_font(h1, 12, bold=True)
    h1.font.all_caps = False
    h1.paragraph_format.space_before = Pt(8)
    h1.paragraph_format.space_after = Pt(3)
    h1.paragraph_format.keep_with_next = True

    bullet = doc.styles["List Bullet"]
    _set_font(bullet, BODY_PT)
    bullet.paragraph_format.space_after = Pt(1)


def _para(doc, text: str, *, bold: bool = False, size: float | None = None, align=None, keep: bool = False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    if align is not None:
        p.alignment = align
    if keep:
        p.paragraph_format.keep_with_next = True
    return p


def _heading(doc, text: str) -> None:
    _bottom_border(doc.add_heading(text, level=1))


def render_docx(content: ResumeContent, out: Path) -> Path:
    doc = Document()
    _setup(doc)

    _para(doc, content.name, bold=True, size=18, align=WD_ALIGN_PARAGRAPH.CENTER)
    if content.headline:
        _para(doc, content.headline, size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
    _para(doc, content.contact_line, align=WD_ALIGN_PARAGRAPH.CENTER)

    for section in content.sections():
        _heading(doc, section)
        if section == "Summary":
            _para(doc, content.summary)
        elif section == "Experience":
            for i, role in enumerate(content.experience):
                title = _para(doc, role.title, bold=True, keep=True)
                if i:
                    title.paragraph_format.space_before = Pt(5)
                _para(doc, role.meta_line, keep=bool(role.bullets))
                for b in role.bullets:
                    doc.add_paragraph(b, style="List Bullet")
        elif section == "Skills":
            for group in content.skills:
                p = doc.add_paragraph()
                p.add_run(f"{group.category}: ").bold = True
                p.add_run(", ".join(group.skills))
        else:
            lines = {
                "Certifications": content.certifications,
                "Education": content.education,
                "Projects": content.projects,
            }[section]
            for line in lines:
                doc.add_paragraph(line, style="List Bullet")

    props = doc.core_properties
    props.author = props.last_modified_by = content.name
    props.title = f"{content.name} Resume"
    props.comments = ""
    # Fixed timestamps keep rebuilds byte-stable apart from the zip metadata.
    props.created = props.modified = datetime(2000, 1, 1)

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out
