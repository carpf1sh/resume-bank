"""Convert a rendered .docx to a text-based PDF with LibreOffice (headless)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
]


class SofficeNotFound(RuntimeError):
    pass


def find_soffice() -> str | None:
    """`RMGR_SOFFICE`, then PATH, then the usual install locations."""
    if env := os.environ.get("RMGR_SOFFICE"):
        return env if Path(env).is_file() else None
    for name in ("soffice", "libreoffice"):
        if found := shutil.which(name):
            return found
    return next((c for c in CANDIDATES if Path(c).is_file()), None)


def require_soffice() -> str:
    if (soffice := find_soffice()) is None:
        raise SofficeNotFound(
            "LibreOffice (soffice) not found. Install it (winget install --id TheDocumentFoundation.LibreOffice -e) "
            "or set RMGR_SOFFICE to soffice's path."
        )
    return soffice


def render_pdf(docx: Path, out: Path, timeout: int = 180) -> Path:
    soffice = require_soffice()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        # A throwaway profile, so conversion works even while LibreOffice is open elsewhere.
        profile = (tmp_dir / "profile").as_uri()
        cmd = [
            soffice,
            f"-env:UserInstallation={profile}",
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(tmp_dir),
            str(docx.resolve()),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        produced = tmp_dir / f"{docx.stem}.pdf"
        if not produced.is_file():
            raise RuntimeError(f"soffice did not produce a PDF (exit {result.returncode}): {result.stderr.strip()}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, out)
    return out
