"""ATS check: re-extract the rendered docx/PDF and confirm a parser sees what we meant.

Checks:
- structure: no tables, text boxes, graphics, or multi-column sections; header/footer empty
- text: every line of the resume survives extraction from the docx and the PDF
- sections: standard headings appear in the expected order
- pages: the PDF is 2 pages or fewer
- keywords: posting terms (via data/skills.yaml names + aliases, plus posting frontmatter
  `keywords`) that the resume does or does not contain. Informational: a missing keyword is a
  gap for /tailor to report, not something to stuff in.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from .models import SkillsTaxonomy
from .resume_doc import ResumeContent

MAX_PAGES = 2
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "•": "", " ": " "})


def _squash(text: str) -> str:
    """Normalize for comparison: NFKC (ligatures), plain quotes/dashes, case, no whitespace."""
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE).lower()
    return re.sub(r"\s+", "", text)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class KeywordHit:
    keyword: str
    posting_terms: list[str]
    resume_terms: list[str]

    @property
    def covered(self) -> bool:
        return bool(self.resume_terms)


@dataclass
class AtsReport:
    checks: list[Check] = field(default_factory=list)
    pages: int | None = None
    keywords: list[KeywordHit] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def coverage(self) -> float | None:
        if not self.keywords:
            return None
        return sum(k.covered for k in self.keywords) / len(self.keywords)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "pages": self.pages,
            "checks": [c.__dict__ for c in self.checks],
            "coverage": self.coverage,
            "keywords": [
                {"keyword": k.keyword, "covered": k.covered, "posting_terms": k.posting_terms, "resume_terms": k.resume_terms}
                for k in self.keywords
            ],
        }


# --- extraction ---------------------------------------------------------------


def docx_text(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def pdf_text(path: Path) -> tuple[str, int]:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)


# --- checks -------------------------------------------------------------------


def check_structure(path: Path) -> list[Check]:
    doc = Document(str(path))
    body = doc.element.body
    problems = []
    if body.findall(f".//{W}tbl"):
        problems.append("tables")
    if body.findall(f".//{W}txbxContent"):
        problems.append("text boxes")
    if body.findall(f".//{W}drawing") or body.findall(f".//{W}pict"):
        problems.append("graphics")
    for cols in body.findall(f".//{W}cols"):
        if int(cols.get(f"{W}num", "1")) > 1:
            problems.append("multiple columns")
    checks = [Check("layout", not problems, "found " + ", ".join(problems) if problems else "single column, plain paragraphs")]

    hf_text = []
    for section in doc.sections:
        for part in (section.header, section.footer, section.first_page_header, section.first_page_footer):
            hf_text += [p.text for p in part.paragraphs if p.text.strip()]
    checks.append(Check("header/footer empty", not hf_text, "; ".join(hf_text)[:120]))
    return checks


def check_text(label: str, extracted: str, content: ResumeContent) -> Check:
    haystack = _squash(extracted)
    missing = [line for line in content.lines() if _squash(line) not in haystack]
    detail = f"{len(content.lines()) - len(missing)}/{len(content.lines())} lines found"
    if missing:
        detail += "; missing: " + " / ".join(m[:60] for m in missing[:5])
    return Check(f"{label} text round-trip", not missing, detail)


def check_sections(label: str, extracted: str, content: ResumeContent) -> Check:
    lines = [ln.strip().lower() for ln in extracted.splitlines()]
    positions = []
    for heading in content.sections():
        try:
            positions.append((heading, lines.index(heading.lower())))
        except ValueError:
            return Check(f"{label} section order", False, f"heading '{heading}' not found on its own line")
    found = [h for h, _ in sorted(positions, key=lambda hp: hp[1])]
    ok = found == content.sections()
    return Check(f"{label} section order", ok, " > ".join(found))


# --- keywords -----------------------------------------------------------------


def _term_re(term: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.I)


def _found(terms: list[str], text: str) -> list[str]:
    return [t for t in terms if _term_re(t).search(text)]


def keyword_coverage(
    posting: str, resume: str, skills: SkillsTaxonomy | None, extra: list[str] = ()
) -> list[KeywordHit]:
    hits: list[KeywordHit] = []
    seen: set[str] = set()
    for cat in skills.categories if skills else []:
        for skill in cat.skills:
            terms = [skill.name, *skill.aliases]
            if in_posting := _found(terms, posting):
                hits.append(KeywordHit(skill.name, in_posting, _found(terms, resume)))
                seen.update(t.lower() for t in terms)
    for kw in extra:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            hits.append(KeywordHit(kw, [kw], _found([kw], resume)))
    return hits


def run_ats_check(
    content: ResumeContent,
    docx: Path,
    pdf: Path | None,
    posting: str = "",
    skills: SkillsTaxonomy | None = None,
    extra_keywords: list[str] = (),
) -> AtsReport:
    report = AtsReport()
    report.checks += check_structure(docx)

    dtext = docx_text(docx)
    report.checks.append(check_text("docx", dtext, content))
    report.checks.append(check_sections("docx", dtext, content))

    if pdf is not None and pdf.is_file():
        ptext, report.pages = pdf_text(pdf)
        report.checks.append(check_text("pdf", ptext, content))
        report.checks.append(check_sections("pdf", ptext, content))
        report.checks.append(Check("page count", report.pages <= MAX_PAGES, f"{report.pages} (max {MAX_PAGES})"))
    else:
        report.checks.append(Check("page count", False, "no PDF to count pages; run `rmgr build resume` with LibreOffice"))

    if posting:
        report.keywords = keyword_coverage(posting, "\n".join(content.lines()), skills, extra_keywords)
    return report
