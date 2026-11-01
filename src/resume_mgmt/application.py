"""Application folders: `applications/YYYY-MM-DD-<company>-<role>/`.

`posting.md` is a frozen copy of the job posting: YAML frontmatter
(`PostingMeta`) plus the description as Markdown. `status.yaml` tracks the stage.

The application log (every `status.yaml`) and the inbox check (`jobs/inbox/*.md`
against the posting contract in docs/job-posting-contract.md) live here too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from docx import Document
from pydantic import ValidationError

from .extract import extract
from .models import ApplicationStatus, PostingMeta, StatusEvent

FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)


@dataclass
class Posting:
    meta: PostingMeta
    body: str


def slugify(text: str, max_words: int = 6) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower().replace("&", " "))
    return "-".join(words[:max_words])


def parse_posting(text: str) -> tuple[dict, str]:
    """Split Markdown into (frontmatter dict, body). No frontmatter gives ({}, text)."""
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def read_posting(path: Path) -> Posting:
    meta, body = parse_posting(path.read_text(encoding="utf-8"))
    return Posting(PostingMeta.model_validate(meta), body)


def _docx_markdown(path: Path) -> str:
    """Keep the posting's headings and lists, which `analysis.md` refers back to."""
    out: list[str] = []
    for p in Document(str(path)).paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name if p.style is not None else "").lower()
        if style.startswith("heading"):
            level = style.removeprefix("heading").strip()
            hashes = "#" if level == "1" else "##"
            out += ["", f"{hashes} {text}", ""]
        elif "list" in style or (p._p.pPr is not None and p._p.pPr.numPr is not None):
            out.append(f"- {text}")
        else:
            out += [text, ""]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def load_source(path: Path) -> tuple[dict, str]:
    """Frontmatter and Markdown body from a posting file (.md, .txt, .docx, .pdf)."""
    suffix = path.suffix.lower()
    if suffix == ".md":
        return parse_posting(path.read_text(encoding="utf-8"))
    if suffix == ".docx":
        return {}, _docx_markdown(path)
    return {}, extract(path)


def new_application(
    root: Path,
    source: Path,
    company: str | None = None,
    title: str | None = None,
    url: str | None = None,
    on: date | None = None,
    role_slug: str | None = None,
) -> Path:
    """Create the application folder with a frozen posting.md and a drafted status.yaml."""
    on = on or date.today()
    meta, body = load_source(source)
    if company:
        meta["company"] = company
    if title:
        meta["title"] = title
    if url:
        meta["url"] = url
    meta.setdefault("source", source.resolve().relative_to(root.resolve()).as_posix()
                    if source.resolve().is_relative_to(root.resolve()) else source.name)
    posting = PostingMeta.model_validate(meta)  # fails early if company/title are missing

    folder = root / "applications" / f"{on.isoformat()}-{slugify(posting.company, 3)}-{role_slug or slugify(posting.title)}"
    if folder.exists():
        raise FileExistsError(f"{folder.relative_to(root).as_posix()} already exists")
    folder.mkdir(parents=True)

    front = yaml.safe_dump(posting.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
                           sort_keys=False, allow_unicode=True).strip()
    (folder / "posting.md").write_text(f"---\n{front}\n---\n\n{body.strip()}\n", encoding="utf-8", newline="\n")

    status = ApplicationStatus(
        company=posting.company,
        title=posting.title,
        url=posting.url,
        created=on,
        history=[StatusEvent(date=on, stage="drafted", note="application folder created")],
    )
    write_status(folder, status)
    return folder


def write_status(folder: Path, status: ApplicationStatus) -> None:
    data = status.model_dump(mode="json", exclude_none=True)
    (folder / "status.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n"
    )


# --- application log and inbox ----------------------------------------------


def normalize_url(url: str | None) -> str | None:
    """Compare posting URLs without scheme, query, fragment, `www.` or a trailing slash."""
    if not url:
        return None
    u = urlsplit(url.strip())
    host = u.netloc.lower().removeprefix("www.")
    return f"{host}{u.path.rstrip('/')}" or None


def dedupe_key(company: str, title: str) -> str:
    return f"{slugify(company, 3)}/{slugify(title, 10)}"


@dataclass
class LogEntry:
    folder: str
    status: ApplicationStatus

    @property
    def updated(self) -> date:
        return max([self.status.created, *(e.date for e in self.status.history)])

    def to_dict(self) -> dict:
        s = self.status
        return {
            "folder": self.folder,
            "company": s.company,
            "title": s.title,
            "url": s.url,
            "stage": s.stage,
            "created": s.created.isoformat(),
            "updated": self.updated.isoformat(),
        }


CLOSED_STAGES = {"rejected", "withdrawn", "closed"}


def application_log(statuses: dict[str, ApplicationStatus]) -> list[LogEntry]:
    """Every application, most recently updated first."""
    entries = [LogEntry(folder, st) for folder, st in statuses.items()]
    return sorted(entries, key=lambda e: (e.updated, e.folder), reverse=True)


@dataclass
class InboxItem:
    path: str
    meta: PostingMeta | None
    error: str | None = None
    duplicate_of: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "company": self.meta.company if self.meta else None,
            "title": self.meta.title if self.meta else None,
            "url": self.meta.url if self.meta else None,
            "error": self.error,
            "duplicate_of": self.duplicate_of,
        }


def read_inbox(root: Path, statuses: dict[str, ApplicationStatus]) -> list[InboxItem]:
    """Check jobs/inbox/*.md against the posting contract and the application log.

    A posting is a duplicate when its URL or its company + title matches an
    existing application (or an earlier inbox file).
    """
    by_url: dict[str, str] = {}
    by_key: dict[str, str] = {}
    for folder, st in statuses.items():
        if (u := normalize_url(st.url)) is not None:
            by_url[u] = folder
        by_key[dedupe_key(st.company, st.title)] = folder

    items: list[InboxItem] = []
    for path in sorted((root / "jobs" / "inbox").glob("*.md")):
        rel = path.relative_to(root).as_posix()
        meta, _ = parse_posting(path.read_text(encoding="utf-8"))
        if not meta:
            items.append(InboxItem(rel, None, "no YAML frontmatter (see docs/job-posting-contract.md)"))
            continue
        try:
            posting = PostingMeta.model_validate(meta)
        except ValidationError as e:
            errs = "; ".join(f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}" for err in e.errors())
            items.append(InboxItem(rel, None, errs))
            continue
        u, key = normalize_url(posting.url), dedupe_key(posting.company, posting.title)
        item = InboxItem(rel, posting, duplicate_of=(by_url.get(u) if u else None) or by_key.get(key))
        if u is not None:
            by_url.setdefault(u, rel)
        by_key.setdefault(key, rel)
        items.append(item)
    return items


def set_stage(folder: Path, stage: str, note: str | None = None, on: date | None = None) -> ApplicationStatus:
    """Move an application to `stage` and append a history entry."""
    path = folder / "status.yaml"
    status = ApplicationStatus.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    on = on or date.today()
    event = StatusEvent(date=on, stage=stage, note=note)  # validates the stage name
    status.stage = event.stage
    status.history.append(event)
    write_status(folder, status)
    return status
