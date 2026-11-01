from pathlib import Path

from resume_mgmt.leak_scan import scan_tree
from resume_mgmt.validate import validate

from test_site import PUBLIC_TEXT, bank  # noqa: F401  (fixture)


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


def test_extra_terms(bank: Path, tmp_path_factory):
    (bank / "leak-terms.txt").write_text("# interview-only names\nProject Nightjar\n", encoding="utf-8")
    tree = _tree(tmp_path_factory.mktemp("tool"), {"x.md": "about project  nightjar"})
    assert [h.what for h in scan_tree(validate(bank), tree)] == ["leak-terms.txt term"]
