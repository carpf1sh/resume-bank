"""`rmgr` command line interface."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import typer

from .models import EXPORTED_SCHEMAS
from .validate import validate as run_validate

app = typer.Typer(help="Resume management: validate the bank and build outputs.", no_args_is_help=True)

new_app = typer.Typer(help="Create new items.", no_args_is_help=True)
build_app = typer.Typer(help="Build outputs.", no_args_is_help=True)
app.add_typer(new_app, name="new")
app.add_typer(build_app, name="build")

RootOption = typer.Option(Path("."), "--root", help="Repository root", file_okay=False, exists=True)
AppDirArg = typer.Argument(..., help="Application folder, e.g. applications/2026-10-31-acme-architect", file_okay=False, exists=True)


def _load_ok(root: Path):
    bank = run_validate(root)
    if bank.errors:
        for e in bank.errors:
            typer.secho(f"error    {e}", fg=typer.colors.RED)
        typer.secho("bank has validation errors; fix them first", fg=typer.colors.RED)
        raise typer.Exit(1)
    return bank


def _outputs(app_dir: Path, stem: str) -> dict[str, Path]:
    return {ext: app_dir / f"{stem}.{ext}" for ext in ("docx", "pdf", "md", "txt")}


@app.command()
def validate(root: Path = RootOption, strict: bool = typer.Option(False, help="Treat warnings as errors")) -> None:
    """Validate every file in data/ and applications/."""
    bank = run_validate(root)
    for w in bank.warnings:
        typer.secho(f"warning  {w}", fg=typer.colors.YELLOW)
    for e in bank.errors:
        typer.secho(f"error    {e}", fg=typer.colors.RED)

    counts = (
        f"{len(bank.roles)} roles, {len(bank.accomplishments)} accomplishments, "
        f"{len(bank.certifications.certifications)} certifications, {len(bank.projects)} projects, "
        f"{len(bank.tailored)} tailored resumes"
    )
    failed = bool(bank.errors) or (strict and bool(bank.warnings))
    if failed:
        typer.secho(f"FAILED: {len(bank.errors)} errors, {len(bank.warnings)} warnings ({counts})", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"OK: {counts}", fg=typer.colors.GREEN)


@app.command()
def gaps(
    root: Path = RootOption,
    limit: int = typer.Option(25, help="Show at most this many gaps (0 = all)"),
    kind: list[str] = typer.Option(None, help="Only these kinds (repeatable)"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Rank weak spots in the bank: thin domains/roles, missing results, unverified metrics."""
    from .gaps import find_gaps

    bank = run_validate(root)
    if bank.errors:
        typer.secho("bank has validation errors; run `rmgr validate` first", fg=typer.colors.RED)
        raise typer.Exit(1)
    found = [g for g in find_gaps(bank) if not kind or g.kind in kind]
    shown = found[:limit] if limit else found
    if as_json:
        typer.echo(json.dumps({"total": len(found), "gaps": [g.to_dict() for g in shown]}, indent=2))
        return
    for g in shown:
        typer.echo(f"{g.priority:4}  {g.kind:18} {g.target}\n      {g.detail}")
    typer.secho(f"{len(shown)} of {len(found)} gaps shown", fg=typer.colors.CYAN)


@app.command()
def extract(root: Path = RootOption) -> None:
    """Extract text from sources/ (docx, pdf, LinkedIn csv) into sources/extracted/."""
    from .extract import extract_all

    failed = False
    for src, out, status in extract_all(root):
        color = typer.colors.RED if status.startswith("error") else None
        failed |= color is not None
        typer.secho(f"{status:10} {src.relative_to(root).as_posix()}", fg=color)
    if failed:
        raise typer.Exit(1)


@new_app.command("application")
def new_application(
    posting: Path = typer.Argument(..., help="Posting file (.md with frontmatter, .docx, .pdf, .txt)", exists=True, dir_okay=False),
    company: str = typer.Option(None, help="Company (required unless the posting has frontmatter)"),
    title: str = typer.Option(None, help="Job title (required unless the posting has frontmatter)"),
    url: str = typer.Option(None, help="Posting URL"),
    role_slug: str = typer.Option(None, help="Short role part of the folder name (default: from the title)"),
    on: str = typer.Option(None, "--date", help="YYYY-MM-DD (default: today)"),
    root: Path = RootOption,
) -> None:
    """Create applications/YYYY-MM-DD-<company>-<role>/ with a frozen posting.md and status.yaml."""
    from pydantic import ValidationError

    from .application import new_application as create

    try:
        folder = create(root, posting, company, title, url, date.fromisoformat(on) if on else None, role_slug)
    except (FileExistsError, ValidationError) as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"created {folder.resolve().relative_to(root.resolve()).as_posix()}", fg=typer.colors.GREEN)


@app.command()
def applications(
    root: Path = RootOption,
    stage: list[str] = typer.Option(None, help="Only these stages (repeatable)"),
    active: bool = typer.Option(False, help="Hide rejected, withdrawn and closed applications"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output (for a job finder)"),
) -> None:
    """The application log: every applications/*/status.yaml, most recently updated first."""
    from .application import CLOSED_STAGES, application_log

    bank = _load_ok(root)
    entries = [
        e for e in application_log(bank.statuses)
        if (not stage or e.status.stage in stage) and not (active and e.status.stage in CLOSED_STAGES)
    ]
    if as_json:
        typer.echo(json.dumps([e.to_dict() for e in entries], indent=2))
        return
    if not entries:
        typer.echo("no applications")
        return
    rows = [(e.status.company, e.status.title, e.status.stage, e.status.created.isoformat(), e.updated.isoformat())
            for e in entries]
    header = ("COMPANY", "ROLE", "STAGE", "CREATED", "UPDATED")
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    for r in [header, *rows]:
        typer.echo("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    typer.secho(f"{len(entries)} applications", fg=typer.colors.CYAN)


@app.command()
def stage(
    app_dir: Path = AppDirArg,
    new_stage: str = typer.Argument(..., metavar="STAGE", help="drafted, applied, screening, interviewing, offer, rejected, withdrawn, closed"),
    note: str = typer.Option(None, help="History note, e.g. 'applied via Greenhouse'"),
    on: str = typer.Option(None, "--date", help="YYYY-MM-DD (default: today)"),
) -> None:
    """Move an application to a new stage and append it to the status history."""
    from pydantic import ValidationError

    from .application import set_stage

    try:
        status = set_stage(app_dir, new_stage, note, date.fromisoformat(on) if on else None)
    except (FileNotFoundError, ValidationError) as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"{status.company} {status.title}: {status.stage}", fg=typer.colors.GREEN)


@app.command()
def inbox(root: Path = RootOption, as_json: bool = typer.Option(False, "--json", help="Machine-readable output")) -> None:
    """Check jobs/inbox/*.md against the posting contract and flag postings already applied to."""
    from .application import read_inbox

    bank = _load_ok(root)
    items = read_inbox(bank.root, bank.statuses)
    if as_json:
        typer.echo(json.dumps([i.to_dict() for i in items], indent=2))
        return
    for i in items:
        if i.error:
            typer.secho(f"invalid    {i.path}\n           {i.error}", fg=typer.colors.RED)
        elif i.duplicate_of:
            typer.secho(f"duplicate  {i.path}  (of {i.duplicate_of})", fg=typer.colors.YELLOW)
        else:
            typer.echo(f"new        {i.path}  {i.meta.company}: {i.meta.title}")
    fresh = sum(1 for i in items if not i.error and not i.duplicate_of)
    typer.secho(f"{len(items)} postings, {fresh} new", fg=typer.colors.CYAN)


@build_app.command("resume")
def build_resume(app_dir: Path = AppDirArg, root: Path = RootOption, pdf: bool = typer.Option(True, help="Also build the PDF (needs LibreOffice)")) -> None:
    """Render resume.yaml to .docx, .pdf, .md and .txt in the application folder."""
    from .render_docx import render_docx
    from .render_pdf import SofficeNotFound, render_pdf
    from .render_text import render_text
    from .resume_doc import load_content, output_stem

    bank = _load_ok(root)
    content = load_content(bank, app_dir)
    out = _outputs(app_dir, output_stem(content))
    render_docx(content, out["docx"])
    render_text(content, out["md"], out["txt"])
    built = [out["docx"], out["md"], out["txt"]]
    if pdf:
        try:
            built.append(render_pdf(out["docx"], out["pdf"]))
        except SofficeNotFound as e:
            typer.secho(str(e), fg=typer.colors.YELLOW)
    for path in built:
        typer.echo(f"wrote {path.as_posix()}")


@build_app.command("site")
def build_site(
    root: Path = RootOption,
    out: Path = typer.Option(None, help="Output folder (default: <root>/build/site)"),
    base_url: str = typer.Option(None, help="Public URL of the site, for canonical/OG tags (default: profile.site_url)"),
    pdf: bool = typer.Option(True, help="Also build the downloadable PDF resume (needs LibreOffice)"),
) -> None:
    """Render the public portfolio (public items only) and run the leak guard."""
    from .render_pdf import SofficeNotFound
    from .site import SiteLeakError
    from .site import build_site as build

    bank = _load_ok(root)
    base_url = base_url or (bank.profile and bank.profile.site_url)
    if not base_url:
        typer.secho("set site_url in data/profile.yaml or pass --base-url", fg=typer.colors.RED)
        raise typer.Exit(1)
    out = out or root / "build" / "site"
    try:
        written = build(bank, out, base_url if base_url.endswith("/") else base_url + "/", pdf=pdf)
    except SofficeNotFound as e:
        typer.secho(f"{e}\nPass --no-pdf to build the site without the PDF resume.", fg=typer.colors.RED)
        raise typer.Exit(1)
    except (SiteLeakError, FileExistsError) as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1)
    public = sum(a.visibility == "public" for a in bank.accomplishments.values())
    typer.secho(f"wrote {len(written)} files to {out.as_posix()} ({public} public accomplishments); leak guard passed",
                fg=typer.colors.GREEN)


@app.command("site-diff")
def site_diff(
    root: Path = RootOption,
    base: str = typer.Option("origin/main", help="Git ref to compare against (what's already published)"),
) -> None:
    """List what would change on the public site since BASE: newly public, removed, and reworded items."""
    from .site_diff import public_diff

    bank = _load_ok(root)
    try:
        changes = public_diff(bank, base)
    except RuntimeError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1)
    if not changes:
        typer.echo(f"no public changes since {base}")
        return
    for change in changes:
        color = {"added": typer.colors.GREEN, "removed": typer.colors.RED}.get(change.kind, typer.colors.YELLOW)
        typer.secho(f"{change.kind:8} {change.what}", fg=color)
        if change.text:
            typer.echo(f"         {change.text}")


@app.command("leak-scan")
def leak_scan(
    folder: Path = typer.Argument(..., help="Folder to scan, e.g. a checkout of the public tool repo", file_okay=False, exists=True),
    root: Path = RootOption,
) -> None:
    """Fail if FOLDER contains anything from the bank: owner name, contact, ids, employers, bank text."""
    from .leak_scan import scan_tree

    bank = _load_ok(root)
    hits = scan_tree(bank, folder)
    for hit in hits:
        typer.secho(f"leak     {hit.path}: {hit.what}", fg=typer.colors.RED)
    if hits:
        typer.secho(f"FAILED: {len(hits)} leaks in {folder.as_posix()}", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"OK: nothing from the bank found in {folder.as_posix()}", fg=typer.colors.GREEN)


@app.command("ats-check")
def ats_check(
    app_dir: Path = AppDirArg,
    root: Path = RootOption,
    min_coverage: float = typer.Option(0.0, help="Fail if keyword coverage is below this fraction (0-1)"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Re-extract the built docx/PDF: layout, lost text, section order, pages, keyword coverage."""
    from .application import read_posting
    from .ats import run_ats_check
    from .resume_doc import load_content, output_stem

    bank = _load_ok(root)
    content = load_content(bank, app_dir)
    out = _outputs(app_dir, output_stem(content))
    if not out["docx"].is_file():
        typer.secho(f"{out['docx'].as_posix()} not found; run `rmgr build resume` first", fg=typer.colors.RED)
        raise typer.Exit(1)
    tr = bank.tailored[app_dir.resolve().relative_to(bank.root).as_posix()]
    posting = read_posting(app_dir / tr.posting)
    report = run_ats_check(content, out["docx"], out["pdf"], posting.body, bank.skills, posting.meta.keywords)
    coverage_ok = report.coverage is None or report.coverage >= min_coverage

    if as_json:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        for c in report.checks:
            typer.secho(f"{'ok  ' if c.ok else 'FAIL'}  {c.name:24} {c.detail}", fg=None if c.ok else typer.colors.RED)
        if report.keywords:
            covered = [k.keyword for k in report.keywords if k.covered]
            missing = [k.keyword for k in report.keywords if not k.covered]
            typer.echo()
            typer.echo(f"keywords {len(covered)}/{len(report.keywords)} ({report.coverage:.0%})")
            typer.echo(f"  covered: {', '.join(covered) or '-'}")
            typer.secho(f"  missing: {', '.join(missing) or '-'}", fg=typer.colors.YELLOW if missing else None)
    if not (report.ok and coverage_ok):
        raise typer.Exit(1)


@app.command()
def schema(root: Path = RootOption) -> None:
    """Export JSON Schemas for editor validation into schemas/."""
    out = root / "schemas"
    out.mkdir(exist_ok=True)
    for stem, model in EXPORTED_SCHEMAS.items():
        path = out / f"{stem}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8", newline="\n")
        typer.echo(f"wrote {path.as_posix()}")


if __name__ == "__main__":
    app()
