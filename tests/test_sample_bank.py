"""The fictional bank in examples/ is the public demo: it must stay valid and buildable."""

import shutil
from pathlib import Path

from typer.testing import CliRunner

from resume_mgmt.cli import app

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-bank"
APP = "applications/2026-01-15-fabrikam-cloud-security-architect"


def run(*args: str):
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result


def test_sample_bank_validates_strict():
    run("validate", "--strict", "--root", str(SAMPLE))


def test_sample_bank_builds(tmp_path: Path):
    bank = tmp_path / "bank"
    shutil.copytree(SAMPLE, bank)
    run("build", "resume", str(bank / APP), "--root", str(bank), "--no-pdf")
    assert (bank / APP / "Jane-Doe-Resume.docx").is_file()
    run("build", "site", "--root", str(bank), "--no-pdf")
    page = (bank / "build" / "site" / "index.html").read_text(encoding="utf-8")
    assert "multi-account AWS landing zone" in page
    assert "Contoso Bank" not in page  # anonymized employer
    assert "northwind-2026-vendor-escalation" not in page  # private item
    assert (bank / "build" / "site" / "how-it-works.html").is_file()  # site/ overlay
