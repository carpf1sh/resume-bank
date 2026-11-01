"""Resolve a tailored resume.yaml against the bank into renderable content.

Every renderer (docx, Markdown, plain text) and the ATS check work from this
one structure, so they can't disagree about what the resume says.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .load import Bank
from .models import Certification, Degree, Period, TailoredResume

# Standard ATS headings, in render order.
SECTION_ORDER = ["Summary", "Experience", "Skills", "Certifications", "Education", "Projects"]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_month(ym: str | None) -> str:
    if ym in (None, "present"):
        return "Present"
    year, month = ym.split("-")
    return f"{MONTHS[int(month) - 1]} {year}"


def fmt_period(period: Period | None) -> str:
    """`MMM YYYY – MMM YYYY` (en dash), with `Present` for ongoing periods."""
    if period is None:
        return ""
    return f"{fmt_month(period.start)} – {fmt_month(period.end)}"


@dataclass
class RoleEntry:
    title: str
    employer: str
    location: str | None
    dates: str
    bullets: list[str] = field(default_factory=list)

    @property
    def meta_line(self) -> str:
        return " | ".join(p for p in (self.employer, self.location, self.dates) if p)


@dataclass
class SkillGroup:
    category: str
    skills: list[str]

    @property
    def line(self) -> str:
        return f"{self.category}: {', '.join(self.skills)}"


@dataclass
class ResumeContent:
    name: str
    headline: str | None
    contact_line: str
    summary: str
    experience: list[RoleEntry]
    skills: list[SkillGroup]
    certifications: list[str]
    education: list[str]
    projects: list[str]

    def sections(self) -> list[str]:
        """Headings that will appear, in order (empty sections are omitted)."""
        present = {
            "Summary": bool(self.summary),
            "Experience": bool(self.experience),
            "Skills": bool(self.skills),
            "Certifications": bool(self.certifications),
            "Education": bool(self.education),
            "Projects": bool(self.projects),
        }
        return [s for s in SECTION_ORDER if present[s]]

    def lines(self) -> list[str]:
        """Every line of text the rendered resume must contain, in order."""
        out = [self.name]
        if self.headline:
            out.append(self.headline)
        out.append(self.contact_line)
        for section in self.sections():
            out.append(section)
            if section == "Summary":
                out.append(self.summary)
            elif section == "Experience":
                for role in self.experience:
                    out += [role.title, role.meta_line, *role.bullets]
            elif section == "Skills":
                out += [g.line for g in self.skills]
            elif section == "Certifications":
                out += self.certifications
            elif section == "Education":
                out += self.education
            elif section == "Projects":
                out += self.projects
        return out


def display_url(url: str) -> str:
    return url.removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")


def cert_line(c: Certification) -> str:
    """`Name, Issuer, MMM YYYY`. Never the credential id."""
    return ", ".join(p for p in (c.name, c.issuer, fmt_month(c.earned) if c.earned else None) if p)


def degree_line(d: Degree) -> str:
    """`Degree, Field | Institution | YYYY (Honors)`."""
    degree = f"{d.degree}, {d.field}" if d.field else d.degree
    parts = [degree, d.institution]
    if d.period and d.period.end not in (None, "present"):
        parts.append(d.period.end[:4])
    line = " | ".join(parts)
    if d.honors:
        line += f" ({d.honors})"
    return line


def _skill_groups(bank: Bank, skills: list[str]) -> list[SkillGroup]:
    """Group the tailored skill list by data/skills.yaml category, keeping first-seen order."""
    category_of: dict[str, str] = {}
    canonical: dict[str, str] = {}
    if bank.skills:
        for cat in bank.skills.categories:
            for skill in cat.skills:
                for term in [skill.name, *skill.aliases]:
                    category_of.setdefault(term.lower(), cat.name)
                canonical.setdefault(skill.name.lower(), skill.name)
    groups: dict[str, list[str]] = {}
    for s in skills:
        cat = category_of.get(s.lower(), "Other")
        groups.setdefault(cat, []).append(canonical.get(s.lower(), s))
    return [SkillGroup(cat, names) for cat, names in groups.items()]


def build_content(bank: Bank, tr: TailoredResume) -> ResumeContent:
    profile = bank.profile
    if profile is None:
        raise ValueError("data/profile.yaml is missing")

    contact = [profile.contact.location or profile.location, profile.contact.email, profile.contact.phone]
    contact += [display_url(link.url) for link in profile.links]

    roles = [(bank.roles[t.role_id], t) for t in tr.roles]
    # Reverse chronological: ATS parsers and recruiters both expect it.
    roles.sort(key=lambda rt: (rt[0].period.end_or_max(), rt[0].period.start), reverse=True)
    experience = [
        RoleEntry(
            title=role.title,
            employer=role.employer,  # resumes are private: the real name, not public_employer
            location=role.location,
            dates=fmt_period(role.period),
            bullets=[] if t.condensed else [b.text.strip() for b in t.bullets],
        )
        for role, t in roles
    ]

    certs = {c.id: c for c in bank.certifications.certifications}
    certifications = [cert_line(certs[cid]) for cid in tr.certifications]

    education = []
    if tr.include_education:
        for d in bank.education.education:
            if d.visibility != "private":
                education.append(degree_line(d))

    projects = []
    for pid in tr.projects:
        p = bank.projects[pid]
        projects.append(f"{p.name}: {p.description.strip()}")

    return ResumeContent(
        name=profile.name,
        headline=profile.headline,
        contact_line=" | ".join(c for c in contact if c),
        summary=" ".join(tr.summary.split()),
        experience=experience,
        skills=_skill_groups(bank, tr.skills),
        certifications=certifications,
        education=education,
        projects=projects,
    )


def output_stem(content: ResumeContent) -> str:
    """File name stem for rendered resumes, e.g. `Jane-Doe-Resume`."""
    return "-".join(content.name.split()) + "-Resume"


def load_content(bank: Bank, app_dir: Path) -> ResumeContent:
    rel = app_dir.resolve().relative_to(bank.root).as_posix()
    tr = bank.tailored.get(rel)
    if tr is None:
        raise ValueError(f"{rel}/resume.yaml not found or invalid")
    return build_content(bank, tr)
