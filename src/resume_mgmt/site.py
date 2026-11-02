"""Build the public portfolio site from the bank.

Only `visibility: public` items reach the page, always through `public_text`.
Profile contact details, resume bullets, STAR text and role summaries are
never passed to the templates. The downloadable PDF resume is built from the
same public context (no contact details, no resume bullets). After rendering,
`find_leaks` scans every output file, including the PDF's extracted text, for
anything that must stay private and the build fails (and the output is
deleted) if it finds one.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pypdf import PdfReader

from .load import Bank
from .render_docx import render_docx
from .render_pdf import render_pdf, require_soffice
from .resume_doc import (
    ResumeContent, RoleEntry, SkillGroup, cert_line, degree_line, display_url, fmt_month, fmt_period, output_stem,
)
from .track import CERT, DEGREE, ROLE, anchor, career_track

TEMPLATES = Path(__file__).resolve().parent / "templates" / "site"
# A bank can add pages or override packaged files from this folder under its root.
OVERLAY = "site"

DOMAIN_LABELS = {
    "security-architecture": "Security Architecture",
    "cloud-security": "Cloud Security",
    "ai-security": "AI Security",
    "appsec": "AppSec",
    "iam": "Identity & Access",
    "grc": "GRC",
    "detection-response": "Detection & Response",
    "devsecops": "DevSecOps",
    "data-security": "Data Security",
    "network-security": "Network Security",
    "leadership": "Leadership",
}

# Free text shorter than this is too generic to scan for (it could match ordinary page words).
MIN_SCAN_LEN = 24


class SiteLeakError(Exception):
    def __init__(self, leaks: list[str]):
        self.leaks = leaks
        super().__init__("site output contains private data:\n" + "\n".join(f"  - {x}" for x in leaks))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class SkillIndex:
    """Maps any skill name or alias to its canonical name and category."""

    canonical: dict[str, str] = field(default_factory=dict)
    category: dict[str, str] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)  # category order from skills.yaml

    @classmethod
    def from_bank(cls, bank: Bank) -> SkillIndex:
        idx = cls()
        for cat in bank.skills.categories if bank.skills else []:
            idx.order.append(cat.name)
            for skill in cat.skills:
                for name in [skill.name, *skill.aliases]:
                    idx.canonical[name.lower()] = skill.name
                idx.category[skill.name] = cat.name
        return idx

    def resolve(self, name: str) -> str:
        return self.canonical.get(name.lower(), name)


# --- context ------------------------------------------------------------------


def shown_skills(obj) -> list[str]:
    """Skills tagged on the site: an accomplishment's `public_skills` override, else its `skills`."""
    override = getattr(obj, "public_skills", None)
    return obj.skills if override is None else override


def _item(text: str, skills: list[str], domains: list[str], idx: SkillIndex) -> dict:
    names = sorted({idx.resolve(s) for s in skills}, key=str.lower)
    return {
        "text": text,
        "skills": [{"name": n, "slug": slug(n)} for n in names],
        "domains": [{"slug": d, "label": DOMAIN_LABELS.get(d, d)} for d in domains],
        "filter_skills": " ".join(slug(n) for n in names),
        "filter_domains": " ".join(domains),
    }


def _span(periods: list) -> str:
    """`2016–now`: the years a domain's evidence covers."""
    starts = [p.start[:4] for p in periods if p]
    if not starts:
        return ""
    ends = [p.end for p in periods if p]
    end = "now" if any(e in (None, "present") for e in ends) else max(e[:4] for e in ends)
    return min(starts) if end == min(starts) else f"{min(starts)}–{end}"


def capabilities(entries: list[tuple], idx: SkillIndex) -> list[dict]:
    """The public evidence grouped by domain, for capabilities.html.

    `entries` are `(obj, text, context, href, period)` for public items only. An item with several
    domains is listed under each, so every section stands on its own; its other domains link across.
    Domains come most-evidenced first, items strongest then newest first.
    """
    sections = []
    for d in DOMAIN_LABELS:
        mine = [e for e in entries if d in e[0].domains]
        if not mine:
            continue
        mine.sort(key=lambda e: e[4].start if e[4] else "", reverse=True)
        mine.sort(key=lambda e: -(getattr(e[0], "strength", None) or 0))
        tally: dict[str, int] = {}
        for obj, *_ in mine:
            for name in {idx.resolve(s) for s in shown_skills(obj)}:
                tally[name] = tally.get(name, 0) + 1
        sections.append({
            "slug": d,
            "label": DOMAIN_LABELS[d],
            "count": len(mine),
            "span": _span([e[4] for e in mine]),
            "roles": len({e[2] for e in mine if hasattr(e[0], "role_id")}),
            "top_skills": [n for n, _ in sorted(tally.items(), key=lambda t: (-t[1], t[0].lower()))[:6]],
            "evidence": [
                {**_item(text, shown_skills(obj), [x for x in obj.domains if x != d], idx),
                 "context": context, "href": href, "dates": fmt_period(period),
                 "year": period.start[:4] if period else ""}
                for obj, text, context, href, period in mine
            ],
        })
    # Stable sort keeps DOMAIN_LABELS order between domains with equal evidence.
    return sorted(sections, key=lambda s: -s["count"])


def site_context(bank: Bank, base_url: str, today: date | None = None) -> dict:
    """Everything the templates may see. Nothing private goes in here.

    `today` decides which certifications have lapsed: they stay on the page, marked as lapsed,
    but leave the JSON-LD and the PDF resume.
    """
    today = today or date.today()
    month = f"{today.year:04d}-{today.month:02d}"
    profile = bank.profile
    idx = SkillIndex.from_bank(bank)

    public_accs = [a for a in bank.accomplishments.values() if a.visibility == "public"]
    public_projects = sorted(
        (p for p in bank.projects.values() if p.visibility == "public"),
        key=lambda p: p.period.start if p.period else "", reverse=True,
    )

    timeline = []
    evidence_entries = []  # (obj, text, context, href, period) for the capabilities page
    for role in sorted(bank.roles.values(), key=lambda r: r.period.start, reverse=True):
        if role.track != "security":
            continue
        accs = sorted(
            (a for a in public_accs if a.role_id == role.id),
            key=lambda a: (-(a.strength or 0), a.period.start if a.period else ""),
        )
        employer = role.public_employer or role.employer
        role_id = anchor(ROLE, employer, role.title)
        evidence_entries += [
            (a, a.public_text, f"{role.title} · {employer}", f"./#{role_id}", a.period or role.period) for a in accs
        ]
        timeline.append({
            "id": role_id,
            "title": role.title,
            "employer": employer,
            "dates": fmt_period(role.period),
            "start": role.period.start,
            "highlights": [_item(a.public_text, shown_skills(a), a.domains, idx) for a in accs],
        })

    # Skills matrix: only skills that public evidence demonstrates.
    domains_seen = sorted({d for a in public_accs for d in a.domains} | {d for p in public_projects for d in p.domains},
                          key=lambda d: list(DOMAIN_LABELS).index(d))
    evidence: dict[str, dict[str, int]] = {}
    for obj in [*public_accs, *public_projects]:
        for name in {idx.resolve(s) for s in shown_skills(obj)}:
            row = evidence.setdefault(name, {})
            row["_total"] = row.get("_total", 0) + 1
            for d in obj.domains:
                row[d] = row.get(d, 0) + 1
    by_cat: dict[str, list[dict]] = {}
    for name, row in evidence.items():
        cat = idx.category.get(name, "Other")
        by_cat.setdefault(cat, []).append({
            "name": name, "slug": slug(name), "total": row["_total"],
            "cells": [row.get(d, 0) for d in domains_seen],
        })
    matrix = [
        {"category": cat, "skills": sorted(by_cat[cat], key=lambda s: (-s["total"], s["name"].lower()))}
        for cat in [*idx.order, "Other"] if cat in by_cat
    ]

    certs = sorted(
        (c for c in bank.certifications.certifications if c.visibility == "public"),
        key=lambda c: c.earned or "", reverse=True,
    )
    degrees = [d for d in bank.education.education if d.visibility == "public"]
    projects = [
        {"name": p.name, "url": p.url, "dates": fmt_period(p.period), **_item(p.public_text or p.description, p.skills, p.domains, idx)}
        for p in public_projects
    ]
    evidence_entries += [(p, p.public_text or p.description, f"Project · {p.name}", "./#projects", p.period) for p in public_projects]

    skill_chips = sorted(
        ({"name": n, "slug": slug(n), "count": r["_total"]} for n, r in evidence.items()),
        key=lambda s: (-s["count"], s["name"].lower()),
    )
    domain_chips = [
        {"slug": d, "label": DOMAIN_LABELS[d], "count": sum(d in a.domains for a in public_accs)}
        for d in domains_seen
    ]

    summary = profile.public_summary
    description = summary or (f"{profile.name}, {profile.headline}" if profile.headline else profile.name)
    person = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": profile.name,
        "url": base_url,
        "jobTitle": profile.headline,
        "description": summary,
        "sameAs": [link.url for link in profile.links],
        "knowsAbout": [s["name"] for s in skill_chips[:15]],
        "alumniOf": [{"@type": "CollegeOrUniversity", "name": d.institution} for d in degrees],
        "hasCredential": [
            {"@type": "EducationalOccupationalCredential", "name": c.name,
             "recognizedBy": {"@type": "Organization", "name": c.issuer}}
            for c in certs if not c.lapsed(month)
        ],
    }
    if profile.location:
        person["homeLocation"] = {"@type": "Place", "name": profile.location}
    person = {k: v for k, v in person.items() if v not in (None, [], "")}

    return {
        "name": profile.name,
        "headline": profile.headline,
        "location": profile.location,
        "summary": summary,
        "description": description,
        "links": [{"label": link.label, "url": link.url} for link in profile.links],
        "base_url": base_url,
        "timeline": timeline,
        "track": career_track(bank, today),
        "month": month,
        "domain_chips": domain_chips,
        "skill_chips": skill_chips,
        "matrix_domains": [{"slug": d, "label": DOMAIN_LABELS[d]} for d in domains_seen],
        "matrix": matrix,
        "certifications": [
            {"id": anchor(CERT, c.name), "name": c.name, "issuer": c.issuer, "earned": fmt_month(c.earned) if c.earned else None, "verify_url": c.verify_url,
             "lapsed": fmt_month(c.expires) if c.lapsed(month) else None}
            for c in certs
        ],
        "education": [
            {"id": anchor(DEGREE, d.degree, d.field, d.institution), "institution": d.institution, "degree": d.degree, "field": d.field, "honors": d.honors,
             "dates": fmt_period(d.period)}
            for d in degrees
        ],
        "projects": projects,
        "capabilities": capabilities(evidence_entries, idx),
        "public_count": len(public_accs),
        "bank_count": len(bank.accomplishments),  # a count only, for pages that describe the bank
        "resume_pdf": None,  # file name, set by build_site once the PDF is built
        # </script> can't appear inside the JSON-LD block.
        "json_ld": json.dumps(person, indent=2, ensure_ascii=False).replace("</", "<\\/"),
    }


# --- PDF resume ---------------------------------------------------------------


def public_resume_content(bank: Bank, ctx: dict) -> ResumeContent:
    """The general resume, built only from the public site context.

    It's a full CV: every public highlight, no page cap (unlike tailored resumes). The contact line is the public location and profile links, never
    `profile.contact`. Experience bullets are `public_text`, never `resume_bullets`. Lapsed
    certifications are left out: a resume lists credentials as current.
    """
    certs = sorted(
        (c for c in bank.certifications.certifications if c.visibility == "public" and not c.lapsed(ctx["month"])),
        key=lambda c: c.earned or "", reverse=True,
    )
    return ResumeContent(
        name=ctx["name"],
        headline=ctx["headline"],
        contact_line=" | ".join(filter(None, [ctx["location"], *(display_url(link["url"]) for link in ctx["links"])])),
        summary=" ".join((ctx["summary"] or "").split()),
        experience=[
            RoleEntry(title=r["title"], employer=r["employer"], location=None, dates=r["dates"],
                      bullets=[h["text"] for h in r["highlights"]])
            for r in ctx["timeline"]
        ],
        skills=[SkillGroup(g["category"], [s["name"] for s in g["skills"]]) for g in ctx["matrix"]],
        certifications=[cert_line(c) for c in certs],
        education=[degree_line(d) for d in bank.education.education if d.visibility == "public"],
        projects=[f"{p['name']}: {p['text']}" for p in ctx["projects"]],
    )


def render_resume_pdf(content: ResumeContent, out: Path) -> Path:
    """Render through a throwaway .docx (never published) to a PDF with LibreOffice."""
    with tempfile.TemporaryDirectory() as tmp:
        docx = render_docx(content, Path(tmp) / f"{out.stem}.docx")
        return render_pdf(docx, out)


# --- leak guard ---------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip().lower()


def _word(token: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9-]){re.escape(token.lower())}(?![a-z0-9-])")


def _phone(phone: str) -> re.Pattern | None:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        return None
    # The same digits with any common separators between them.
    return re.compile(r"(?<!\d)" + r"[\s().+-]{0,3}".join(digits) + r"(?!\d)")


def find_leaks(bank: Bank, text: str) -> list[str]:
    """Everything private that shows up in `text` (the concatenated site output)."""
    page = _norm(text)
    leaks: list[str] = []

    contact = bank.profile.contact if bank.profile else None
    if contact:
        if contact.email and contact.email.lower() in page:
            leaks.append("profile.contact.email")
        if contact.phone and (pat := _phone(contact.phone)) and pat.search(page):
            leaks.append("profile.contact.phone")
        # The private location only leaks if it differs from the public one.
        public_loc = (bank.profile.location or "").lower()
        if contact.location and contact.location.lower() != public_loc and contact.location.lower() in page:
            leaks.append("profile.contact.location")

    hidden_ids = [a.id for a in bank.accomplishments.values() if a.visibility != "public"]
    hidden_ids += [c.id for c in bank.certifications.certifications if c.visibility != "public"]
    hidden_ids += [p.id for p in bank.projects.values() if p.visibility != "public"]
    for item_id in hidden_ids:
        if _word(item_id).search(page):
            leaks.append(f"non-public id '{item_id}'")

    for c in bank.certifications.certifications:
        if c.visibility != "public" and _norm(c.name) in page:
            leaks.append(f"non-public certification '{c.id}'")

    for acc in bank.accomplishments.values():
        texts = [("resume_bullets", b) for b in acc.resume_bullets]
        texts += [(f"star.{k}", v) for k, v in acc.star.model_dump().items() if v]
        if acc.visibility != "public" and acc.public_text:
            texts.append(("public_text of a non-public item", acc.public_text))
        for where, value in texts:
            if len(value) >= MIN_SCAN_LEN and _norm(value) in page:
                leaks.append(f"{acc.id} {where}")

    for proj in bank.projects.values():
        if proj.visibility != "public":
            for value in filter(None, [proj.description, proj.public_text]):
                if len(value) >= MIN_SCAN_LEN and _norm(value) in page:
                    leaks.append(f"non-public project '{proj.id}' text")

    for role in bank.roles.values():
        if role.public_employer and role.employer.lower() not in role.public_employer.lower():
            if _word(role.employer).search(page):
                leaks.append(f"anonymized employer of role '{role.id}'")
        if role.summary and len(role.summary) >= MIN_SCAN_LEN and _norm(role.summary) in page:
            leaks.append(f"role summary of '{role.id}'")

    return leaks


def output_text(path: Path) -> str:
    """A built file as text for the leak guard: a PDF's extracted text plus its metadata, else the decoded file."""
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        meta = [str(v) for v in (reader.metadata or {}).values()]
        return "\n".join([*(page.extract_text() or "" for page in reader.pages), *meta])
    return path.read_text(encoding="utf-8", errors="replace")


# --- build --------------------------------------------------------------------


def _clear(out_dir: Path) -> None:
    """Empty a previous build. Refuses to clear a folder that isn't one."""
    if not out_dir.exists():
        return
    if any(out_dir.iterdir()) and not (out_dir / ".nojekyll").is_file():
        raise FileExistsError(f"{out_dir} is not empty and isn't a previous site build (no .nojekyll); not clearing it")
    shutil.rmtree(out_dir)


def build_site(
    bank: Bank, out_dir: Path, base_url: str, templates: Path = TEMPLATES, pdf: bool = True, today: date | None = None,
) -> list[Path]:
    """Render the site into `out_dir`. Raises SiteLeakError (and deletes the output) on a leak.

    Files in the bank's `site/` folder are rendered alongside `templates` and win on a name clash.

    With `pdf`, also renders the general PDF resume, and raises SofficeNotFound before touching
    `out_dir` if LibreOffice is missing: a publish must not silently drop the PDF.
    """
    if bank.profile is None:
        raise ValueError("data/profile.yaml is required to build the site")
    if pdf:
        require_soffice()
    _clear(out_dir)
    out_dir.mkdir(parents=True)
    # Written first so a crashed build still counts as a site build for the next _clear.
    nojekyll = out_dir / ".nojekyll"
    nojekyll.write_text("", encoding="utf-8")

    search = [d for d in (bank.root / OVERLAY, templates) if d.is_dir()]
    sources: dict[Path, Path] = {}
    for base in reversed(search):
        for src in base.rglob("*"):
            if src.is_file() and not src.name.startswith("."):
                sources[src.relative_to(base)] = src
    env = Environment(
        loader=FileSystemLoader(search),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    ctx = site_context(bank, base_url, today)
    ctx["pages"] = sorted(rel.with_suffix("").as_posix() for rel in sources if rel.suffix == ".j2")
    written: list[Path] = []
    if pdf:
        content = public_resume_content(bank, ctx)
        ctx["resume_pdf"] = f"{output_stem(content)}.pdf"
        written.append(render_resume_pdf(content, out_dir / ctx["resume_pdf"]))
    for rel, src in sorted(sources.items()):
        if src.suffix == ".j2":
            dest = out_dir / rel.with_suffix("")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(env.get_template(rel.as_posix()).render(**ctx), encoding="utf-8", newline="\n")
        else:
            dest = out_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        written.append(dest)
    written.append(nojekyll)

    output = "\n".join(output_text(p) for p in written)
    if leaks := find_leaks(bank, output):
        shutil.rmtree(out_dir)
        raise SiteLeakError(leaks)
    return written
