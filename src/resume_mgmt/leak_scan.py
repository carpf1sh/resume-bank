"""Scan a folder (e.g. the public tool repo) for anything that identifies the bank's owner.

Stricter than the site's leak guard: the tool repo should contain nothing from the
bank at all, public or not. It looks for the owner's name, contact details,
every accomplishment, role and project id, every employer, longer free
text (bullets, STAR, summaries, public_text), and any extra terms listed one per
line in `<bank>/leak-terms.txt`. Public link handles (a GitHub username) are not
scanned: the tool repo's own URL and license carry one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .load import Bank
from .site import MIN_SCAN_LEN, _norm, _phone, _word, output_text

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "node_modules"}
EXTRA_TERMS = "leak-terms.txt"


@dataclass(frozen=True)
class Hit:
    path: str
    what: str


def _text_pattern(value: str) -> re.Pattern:
    return re.compile(re.escape(_norm(value)))


def scan_patterns(bank: Bank) -> list[tuple[str, re.Pattern]]:
    """(label, pattern) pairs, matched against normalized (lowercased, whitespace-collapsed) text."""
    pats: list[tuple[str, re.Pattern]] = []
    profile = bank.profile
    if profile:
        pats.append(("profile.name", _word(profile.name)))
        pats += [(f"profile.name part '{p}'", _word(p)) for p in profile.name.split() if len(p) >= 4]
        c = profile.contact
        if c.email:
            pats.append(("profile.contact.email", _word(c.email)))
        if c.phone and (pat := _phone(c.phone)):
            pats.append(("profile.contact.phone", pat))
        for label, loc in (("profile.contact.location", c.location), ("profile.location", profile.location)):
            if loc:
                pats.append((label, _word(loc)))
        texts = [profile.headline, profile.public_summary, *profile.summaries.values()]
        pats += [("profile text", _text_pattern(t)) for t in texts if t and len(t) >= MIN_SCAN_LEN]

    # Certification ids (cissp, aws-saa) are shared vocabulary, not identifying.
    ids = [*bank.accomplishments, *bank.roles, *bank.projects]
    pats += [(f"id '{i}'", _word(i)) for i in ids]

    for role in bank.roles.values():
        pats.append((f"employer of '{role.id}'", _word(role.employer)))
        if role.summary and len(role.summary) >= MIN_SCAN_LEN:
            pats.append((f"summary of '{role.id}'", _text_pattern(role.summary)))

    for acc in bank.accomplishments.values():
        texts = [*acc.resume_bullets, *(v for v in acc.star.model_dump().values() if v), acc.public_text]
        pats += [(f"text of '{acc.id}'", _text_pattern(t)) for t in texts if t and len(t) >= MIN_SCAN_LEN]

    extra = bank.root / EXTRA_TERMS
    if extra.is_file():
        for line in extra.read_text(encoding="utf-8").splitlines():
            term = line.strip()
            if term and not term.startswith("#"):
                pats.append((f"{EXTRA_TERMS} term", _word(term)))
    return pats


def _files(folder: Path):
    for path in sorted(folder.rglob("*")):
        if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(folder).parts):
            yield path


def _read(path: Path) -> str | None:
    if path.suffix.lower() == ".pdf":
        return output_text(path)
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return None  # binary (fonts, images)
    return data.decode("utf-8", errors="replace")


def scan_tree(bank: Bank, folder: Path) -> list[Hit]:
    """Every pattern hit in every text file (and PDF) under `folder`, skipping caches and `.git`."""
    pats = scan_patterns(bank)
    hits: list[Hit] = []
    for path in _files(folder):
        text = _read(path)
        if text is None:
            continue
        page = _norm(text)
        rel = path.relative_to(folder).as_posix()
        hits += [Hit(rel, label) for label, pat in pats if pat.search(page)]
    return hits
