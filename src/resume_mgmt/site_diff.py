"""Compare what the public site shows now with what it showed at a git ref.

The /publish skill uses this to show the owner which items become public before
anything is pushed.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .load import Bank, load_bank


@dataclass
class Change:
    kind: str  # added | removed | changed
    what: str
    text: str | None = None


def public_items(bank: Bank) -> dict[str, str]:
    """Label -> the text the site shows for it, for every public item and public profile field."""
    items: dict[str, str] = {}
    if bank.profile:
        for name in ("name", "headline", "location", "public_summary"):
            if value := getattr(bank.profile, name):
                items[f"profile.{name}"] = value
        for link in bank.profile.links:
            items[f"link {link.label}"] = link.url
    for acc in bank.accomplishments.values():
        if acc.visibility == "public":
            items[f"accomplishment {acc.id}"] = acc.public_text or ""
    for cert in bank.certifications.certifications:
        if cert.visibility == "public":
            items[f"certification {cert.id}"] = cert.name
    for deg in bank.education.education:
        if deg.visibility == "public":
            items[f"education {deg.institution}"] = f"{deg.degree}, {deg.field or ''}".strip(", ")
    for proj in bank.projects.values():
        if proj.visibility == "public":
            items[f"project {proj.id}"] = proj.public_text or proj.description
    for role in bank.roles.values():
        if role.public_employer:
            items[f"role {role.id} employer"] = role.public_employer
    return items


def _bank_at(root: Path, ref: str, tmp: Path) -> Bank:
    proc = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", ref, "data"],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git archive {ref} failed: {proc.stderr.decode(errors='replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        tar.extractall(tmp, filter="data")
    return load_bank(tmp)


def public_diff(bank: Bank, ref: str) -> list[Change]:
    with tempfile.TemporaryDirectory() as tmp:
        old = public_items(_bank_at(bank.root, ref, Path(tmp)))
    new = public_items(bank)
    changes = [Change("added", k, v) for k, v in new.items() if k not in old]
    changes += [Change("changed", k, v) for k, v in new.items() if k in old and old[k] != v]
    changes += [Change("removed", k) for k in old if k not in new]
    return changes
