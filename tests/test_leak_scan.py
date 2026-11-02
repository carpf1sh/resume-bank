from pathlib import Path

from resume_mgmt.leak_scan import scan_tree
from resume_mgmt.validate import validate

from test_site import PUBLIC_TEXT, _fake_pdf, bank  # noqa: F401  (fixture)
from test_validate import ROLE, write


def _tree(tmp: Path, files: dict[str, str | bytes]) -> Path:
    for rel, content in files.items():
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return tmp


def test_clean_tree_passes(bank: Path, tmp_path_factory):
    tree = _tree(tmp_path_factory.mktemp("tool"), {
        "README.md": "A resume bank tool. Example: cspm, CISSP, Jane Doe.",
        "font.woff2": b"\0\1binary Test Person",
    })
    assert scan_tree(validate(bank), tree) == []


def test_catches_bank_content(bank: Path, tmp_path_factory):
    tree = _tree(tmp_path_factory.mktemp("tool"), {
        "a.md": "Written by Test Person",
        "b.py": "EMAIL = 'TEST@example.com'",
        "c.md": "see cspm-rollout",
        "d.md": PUBLIC_TEXT.upper(),
        "e.md": "Worked at Acme",
        ".git/config": "Test Person",
    })
    hits = {(h.path, h.what) for h in scan_tree(validate(bank), tree)}
    assert ("a.md", "profile.name") in hits
    assert ("b.py", "profile.contact.email") in hits
    assert ("c.md", "id 'cspm-rollout'") in hits
    assert any(path == "d.md" for path, _ in hits)
    assert any(path == "e.md" and what.startswith("employer") for path, what in hits)
    assert not any(path.startswith(".git") for path, _ in hits)


def test_catches_role_summary(bank: Path, tmp_path_factory):
    summary = "Owned security architecture for the payments platform"
    write(bank, "data/roles/acme-architect.yaml", {**ROLE, "summary": summary})
    tree = _tree(tmp_path_factory.mktemp("tool"), {"notes.md": summary.lower()})
    assert ("notes.md", "summary of 'acme-architect'") in {(h.path, h.what) for h in scan_tree(validate(bank), tree)}


def test_scans_pdf_text(bank: Path, tmp_path_factory):
    tree = tmp_path_factory.mktemp("tool")
    _fake_pdf(["Prepared by Test Person"], tree / "demo.pdf")
    assert ("demo.pdf", "profile.name") in {(h.path, h.what) for h in scan_tree(validate(bank), tree)}


def test_bank_without_profile_or_contact(bank: Path, tmp_path_factory):
    tree = _tree(tmp_path_factory.mktemp("tool"), {"a.md": "Test Person, Denver, CO, see cspm-rollout"})
    write(bank, "data/profile.yaml", {"name": "Someone Else"})
    assert [h.what for h in scan_tree(validate(bank), tree)] == ["id 'cspm-rollout'"]
    (bank / "data/profile.yaml").unlink()
    assert [h.what for h in scan_tree(validate(bank), tree)] == ["id 'cspm-rollout'"]


def test_extra_terms(bank: Path, tmp_path_factory):
    (bank / "leak-terms.txt").write_text("# interview-only names\nProject Nightjar\n", encoding="utf-8")
    tree = _tree(tmp_path_factory.mktemp("tool"), {"x.md": "about project  nightjar"})
    assert [h.what for h in scan_tree(validate(bank), tree)] == ["leak-terms.txt term"]
