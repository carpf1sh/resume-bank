"""Load the bank from disk into models, collecting per-file errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from .models import (
    Accomplishment,
    ApplicationStatus,
    Certifications,
    Education,
    Profile,
    Project,
    Role,
    SkillsTaxonomy,
    TailoredResume,
)

M = TypeVar("M", bound=BaseModel)


@dataclass
class Issue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass
class Bank:
    root: Path
    profile: Profile | None = None
    skills: SkillsTaxonomy | None = None
    certifications: Certifications = field(default_factory=Certifications)
    education: Education = field(default_factory=Education)
    roles: dict[str, Role] = field(default_factory=dict)
    accomplishments: dict[str, Accomplishment] = field(default_factory=dict)
    projects: dict[str, Project] = field(default_factory=dict)
    tailored: dict[str, TailoredResume] = field(default_factory=dict)
    statuses: dict[str, ApplicationStatus] = field(default_factory=dict)
    # Repo-relative path each id was loaded from.
    paths: dict[str, str] = field(default_factory=dict)
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _read(bank: Bank, path: Path, model: type[M]) -> M | None:
    rel = _rel(bank.root, path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        bank.errors.append(Issue(rel, f"invalid YAML: {e}"))
        return None
    if raw is None:
        bank.errors.append(Issue(rel, "file is empty"))
        return None
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(root)"
            bank.errors.append(Issue(rel, f"{loc}: {err['msg']}"))
        return None


def _yaml_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.rglob("*.yaml") if p.is_file())


def _add(bank: Bank, kind: dict, item, path: Path) -> None:
    rel = _rel(bank.root, path)
    if item.id in bank.paths:
        bank.errors.append(Issue(rel, f"duplicate id '{item.id}' (also in {bank.paths[item.id]})"))
        return
    bank.paths[item.id] = rel
    kind[item.id] = item


def load_bank(root: Path) -> Bank:
    root = root.resolve()
    bank = Bank(root=root)
    data = root / "data"

    singletons = [
        ("profile.yaml", Profile, "profile"),
        ("skills.yaml", SkillsTaxonomy, "skills"),
        ("certifications.yaml", Certifications, "certifications"),
        ("education.yaml", Education, "education"),
    ]
    for name, model, attr in singletons:
        path = data / name
        if path.is_file():
            if (obj := _read(bank, path, model)) is not None:
                setattr(bank, attr, obj)
        else:
            bank.warnings.append(Issue(f"data/{name}", "not found (create it during /ingest)"))

    for path in _yaml_files(data / "roles"):
        if (role := _read(bank, path, Role)) is not None:
            _add(bank, bank.roles, role, path)

    for path in _yaml_files(data / "accomplishments"):
        if (acc := _read(bank, path, Accomplishment)) is not None:
            _add(bank, bank.accomplishments, acc, path)

    for path in _yaml_files(data / "projects"):
        if (proj := _read(bank, path, Project)) is not None:
            _add(bank, bank.projects, proj, path)

    for path in sorted((root / "applications").glob("*/resume.yaml")):
        if (tr := _read(bank, path, TailoredResume)) is not None:
            bank.tailored[_rel(root, path.parent)] = tr

    for path in sorted((root / "applications").glob("*/status.yaml")):
        if (st := _read(bank, path, ApplicationStatus)) is not None:
            bank.statuses[_rel(root, path.parent)] = st

    return bank
