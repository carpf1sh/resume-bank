"""Render resume content as Markdown and as plain text (for pasting into application forms)."""

from __future__ import annotations

from pathlib import Path

from .resume_doc import ResumeContent


def _md_escape(text: str) -> str:
    # Lines starting with these would turn into Markdown structure.
    return "\\" + text if text[:1] in "#>+-*|" else text


def to_markdown(content: ResumeContent) -> str:
    out = [f"# {content.name}", ""]
    if content.headline:
        out += [f"**{content.headline}**", ""]
    out += [content.contact_line, ""]
    for section in content.sections():
        out += [f"## {section}", ""]
        if section == "Summary":
            out += [content.summary, ""]
        elif section == "Experience":
            for role in content.experience:
                out += [f"### {role.title}", "", role.meta_line, ""]
                if role.bullets:
                    out += [f"- {b}" for b in role.bullets] + [""]
        elif section == "Skills":
            out += [f"- **{g.category}:** {', '.join(g.skills)}" for g in content.skills] + [""]
        else:
            lines = {
                "Certifications": content.certifications,
                "Education": content.education,
                "Projects": content.projects,
            }[section]
            out += [f"- {_md_escape(line)}" for line in lines] + [""]
    return "\n".join(out).rstrip() + "\n"


def to_text(content: ResumeContent) -> str:
    out = [content.name]
    if content.headline:
        out.append(content.headline)
    out += [content.contact_line, ""]
    for section in content.sections():
        out += [section.upper(), ""]
        if section == "Summary":
            out += [content.summary, ""]
        elif section == "Experience":
            for role in content.experience:
                out += [role.title, role.meta_line]
                out += [f"- {b}" for b in role.bullets]
                out.append("")
        elif section == "Skills":
            out += [g.line for g in content.skills] + [""]
        else:
            lines = {
                "Certifications": content.certifications,
                "Education": content.education,
                "Projects": content.projects,
            }[section]
            out += [f"- {line}" for line in lines] + [""]
    return "\n".join(out).rstrip() + "\n"


def render_text(content: ResumeContent, md_out: Path, txt_out: Path) -> tuple[Path, Path]:
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(to_markdown(content), encoding="utf-8", newline="\n")
    txt_out.write_text(to_text(content), encoding="utf-8", newline="\n")
    return md_out, txt_out
