"""Cross-file rules that a single model can't check on its own."""

from __future__ import annotations

import re
from pathlib import Path

from .load import Bank, Issue, load_bank

MAX_BULLET_WORDS = 25
APP_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*$")

def _check_sources(bank: Bank, rel: str, sources: list[str]) -> None:
    for src in sources:
        if not (bank.root / src).exists():
            bank.errors.append(Issue(rel, f"source not found: {src}"))


def _check_roles(bank: Bank) -> None:
    for role in bank.roles.values():
        rel = bank.paths[role.id]
        if Path(rel).stem != role.id:
            bank.errors.append(Issue(rel, f"file name must match id '{role.id}'"))
        _check_sources(bank, rel, role.sources)


def _check_accomplishments(bank: Bank) -> None:
    known_skills = bank.skills.all_names() if bank.skills else None
    for acc in bank.accomplishments.values():
        rel = bank.paths[acc.id]
        expected = f"data/accomplishments/{acc.role_id}/{acc.id}.yaml"
        if rel != expected:
            bank.errors.append(Issue(rel, f"must live at {expected}"))

        role = bank.roles.get(acc.role_id)
        if role is None:
            bank.errors.append(Issue(rel, f"unknown role_id '{acc.role_id}'"))
        elif acc.period and not role.period.contains(acc.period):
            bank.errors.append(
                Issue(rel, f"period {acc.period.start}..{acc.period.end} is outside role '{role.id}'")
            )

        _check_sources(bank, rel, acc.sources)

        if acc.public_skills is not None:
            extra = sorted(set(acc.public_skills) - set(acc.skills))
            if extra:
                bank.errors.append(Issue(rel, f"public_skills must be a subset of skills; not in skills: {', '.join(extra)}"))

        if known_skills is not None:
            unknown = [s for s in acc.skills if s.lower() not in known_skills]
            if unknown:
                bank.warnings.append(Issue(rel, f"skills not in data/skills.yaml: {', '.join(unknown)}"))


def _check_certifications(bank: Bank) -> None:
    for cert in bank.certifications.certifications:
        if cert.id in bank.paths:
            bank.errors.append(
                Issue("data/certifications.yaml", f"duplicate id '{cert.id}' (also in {bank.paths[cert.id]})")
            )
        else:
            bank.paths[cert.id] = "data/certifications.yaml"


def _check_projects(bank: Bank) -> None:
    for proj in bank.projects.values():
        rel = bank.paths[proj.id]
        if proj.visibility == "public" and not (proj.public_text or proj.description):
            bank.errors.append(Issue(rel, "public project needs public_text or description"))
        _check_sources(bank, rel, proj.sources)


def _check_tailored(bank: Bank) -> None:
    """Tailored resumes may only cite real, non-private bank entries."""
    cert_ids = {c.id: c for c in bank.certifications.certifications}
    known_skills = bank.skills.all_names() if bank.skills else None
    for app_dir, tr in bank.tailored.items():
        rel = f"{app_dir}/resume.yaml"
        if not (bank.root / app_dir / tr.posting).is_file():
            bank.errors.append(Issue(rel, f"posting not found: {tr.posting}"))
        for trole in tr.roles:
            if trole.role_id not in bank.roles:
                bank.errors.append(Issue(rel, f"unknown role_id '{trole.role_id}'"))
            for bullet in trole.bullets:
                if (words := len(bullet.text.split())) > MAX_BULLET_WORDS:
                    bank.warnings.append(
                        Issue(rel, f"bullet under '{trole.role_id}' runs {words} words (max {MAX_BULLET_WORDS})")
                    )
                for src in bullet.sources:
                    acc = bank.accomplishments.get(src)
                    if acc is None:
                        bank.errors.append(Issue(rel, f"bullet cites unknown accomplishment '{src}'"))
                    elif acc.visibility == "private":
                        bank.errors.append(Issue(rel, f"bullet cites private accomplishment '{src}'"))
                    elif acc.role_id != trole.role_id:
                        bank.errors.append(
                            Issue(rel, f"bullet under '{trole.role_id}' cites '{src}' from '{acc.role_id}'")
                        )
        if known_skills is not None:
            unknown = [s for s in tr.skills if s.lower() not in known_skills]
            if unknown:
                bank.warnings.append(Issue(rel, f"skills not in data/skills.yaml: {', '.join(unknown)}"))
        for cid in tr.certifications:
            cert = cert_ids.get(cid)
            if cert is None:
                bank.errors.append(Issue(rel, f"unknown certification '{cid}'"))
            elif cert.visibility == "private":
                bank.errors.append(Issue(rel, f"private certification '{cid}'"))
            elif APP_DIR.match(Path(app_dir).name) and cert.lapsed(Path(app_dir).name[:7]):
                # Judged at the application's date, so a resume sent while the cert was valid stays valid.
                bank.errors.append(Issue(rel, f"certification '{cid}' had lapsed ({cert.expires})"))
        for pid in tr.projects:
            proj = bank.projects.get(pid)
            if proj is None:
                bank.errors.append(Issue(rel, f"unknown project '{pid}'"))
            elif proj.visibility == "private":
                bank.errors.append(Issue(rel, f"private project '{pid}'"))


def _check_applications(bank: Bank) -> None:
    """Application folders are named YYYY-MM-DD-<company>-<role> and hold a posting and a status."""
    apps = bank.root / "applications"
    if not apps.is_dir():
        return
    for folder in sorted(p for p in apps.iterdir() if p.is_dir()):
        rel = _rel_dir(bank, folder)
        if not APP_DIR.match(folder.name):
            bank.errors.append(Issue(rel, "folder name must be YYYY-MM-DD-<company>-<role>"))
        for name in ("posting.md", "status.yaml"):  # resume.yaml comes later, from /tailor
            if not (folder / name).is_file():
                bank.warnings.append(Issue(rel, f"missing {name}"))
        status = bank.statuses.get(rel)
        if status and status.history:
            if status.history[-1].stage != status.stage:
                bank.warnings.append(Issue(f"{rel}/status.yaml", f"stage '{status.stage}' differs from the last history entry"))
            if any(a.date > b.date for a, b in zip(status.history, status.history[1:])):
                bank.warnings.append(Issue(f"{rel}/status.yaml", "history is not in date order"))


def _check_inbox(bank: Bank) -> None:
    """Postings in jobs/inbox/ must follow docs/job-posting-contract.md. Warnings: they're external input."""
    from .application import read_inbox

    for item in read_inbox(bank.root, bank.statuses):
        if item.error:
            bank.warnings.append(Issue(item.path, item.error))


def _rel_dir(bank: Bank, path: Path) -> str:
    return path.relative_to(bank.root).as_posix()


def validate(root: Path) -> Bank:
    """Load the bank and run every cross-file check. Inspect `.errors` / `.warnings`."""
    bank = load_bank(root)
    _check_roles(bank)
    _check_accomplishments(bank)
    _check_certifications(bank)
    _check_projects(bank)
    _check_tailored(bank)
    _check_applications(bank)
    _check_inbox(bank)
    return bank
