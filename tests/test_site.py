import json
import re
import subprocess
from pathlib import Path

import pytest

from resume_mgmt.render_pdf import find_soffice
from resume_mgmt.site import SiteLeakError, build_site, find_leaks
from resume_mgmt.site_diff import public_diff
from resume_mgmt.validate import validate

from test_validate import ROLE, accomplishment, write

PUBLIC_TEXT = "Rolled out cloud posture management across a multi-cloud estate"


@pytest.fixture
def bank(tmp_path: Path) -> Path:
    write(tmp_path, "sources/resumes/2023-resume.txt", "resume text")
    write(tmp_path, "data/profile.yaml", {
        "name": "Test Person",
        "headline": "Security Architect",
        "location": "Remote, US",
        "public_summary": "Security architect focused on cloud and AI.",
        "contact": {"email": "test@example.com", "phone": "555-010-0123", "location": "Denver, CO"},
        "links": [{"label": "GitHub", "url": "https://github.com/test"}],
    })
    write(tmp_path, "data/skills.yaml", {"categories": [
        {"name": "Cloud Security", "skills": [{"name": "CSPM", "aliases": ["cloud security posture management"]}]},
    ]})
    write(tmp_path, "data/certifications.yaml", {"certifications": [
        {"id": "cissp", "name": "CISSP", "issuer": "ISC2", "earned": "2021-09"},
        {"id": "secret-cert", "name": "Internal Red Badge Program", "issuer": "Acme", "visibility": "resume"},
    ]})
    write(tmp_path, "data/education.yaml", {"education": [{"institution": "State U", "degree": "BS"}]})
    write(tmp_path, "data/roles/acme-architect.yaml", ROLE)
    write(tmp_path, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(
        visibility="public", public_text=PUBLIC_TEXT, skills=["cloud security posture management"],
        domains=["cloud-security"], star={"result": "Cut open critical misconfigurations from 900 to 40 in a quarter"},
    ))
    write(tmp_path, "data/accomplishments/acme-architect/acme-2022-private-incident.yaml", accomplishment(
        id="acme-2022-private-incident", visibility="private",
        resume_bullets=["Contained the ransomware outbreak on the payroll cluster within six hours"],
    ))
    assert validate(tmp_path).errors == []
    return tmp_path


def _build(root: Path) -> str:
    out = root / "build" / "site"
    build_site(validate(root), out, "https://example.test/", pdf=False)
    return (out / "index.html").read_text(encoding="utf-8")


def test_renders_public_items_only(bank: Path):
    page = _build(bank)
    assert PUBLIC_TEXT in page
    assert "Security architect focused on cloud and AI." in page
    assert "CISSP" in page
    assert "Internal Red Badge Program" not in page
    assert "ransomware" not in page
    assert "4,200" not in page  # resume bullet of the public item
    assert "test@example.com" not in page
    assert (bank / "build/site/.nojekyll").is_file()


def test_skill_aliases_resolve_and_filters_render(bank: Path):
    page = _build(bank)
    assert 'data-skills="cspm"' in page
    assert 'data-domains="cloud-security"' in page
    assert 'data-value="cloud-security"' in page


def test_meta_tags_and_json_ld(bank: Path):
    page = _build(bank)
    assert '<meta property="og:url" content="https://example.test/">' in page
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
    assert ld["@type"] == "Person"
    assert ld["name"] == "Test Person"
    assert "email" not in ld and "telephone" not in ld
    assert ld["hasCredential"][0]["name"] == "CISSP"


def test_leak_guard_fails_on_injected_private_item(bank: Path, monkeypatch):
    """Inject a private item into the rendered context: the build must fail and leave no output."""
    import resume_mgmt.site as site

    real = site.site_context

    def leaky(bank_, base_url, today=None):
        ctx = real(bank_, base_url, today)
        private = bank_.accomplishments["acme-2022-private-incident"]
        ctx["timeline"][0]["highlights"].append(site._item(private.resume_bullets[0], [], [], site.SkillIndex()))
        ctx["summary"] = f"Reach me at {bank_.profile.contact.email}, ref acme-2022-private-incident"
        return ctx

    monkeypatch.setattr(site, "site_context", leaky)
    with pytest.raises(SiteLeakError) as exc:
        _build(bank)
    leaks = "\n".join(exc.value.leaks)
    assert "profile.contact.email" in leaks
    assert "non-public id 'acme-2022-private-incident'" in leaks
    assert "acme-2022-private-incident resume_bullets" in leaks
    assert not (bank / "build/site").exists()


@pytest.mark.parametrize("text, leak", [
    ("call 555.010.0123", "profile.contact.phone"),
    ("call (555) 010-0123", "profile.contact.phone"),
    ("based in Denver, CO", "profile.contact.location"),
    ("Internal Red Badge Program", "non-public certification 'secret-cert'"),
    ("see secret-cert", "non-public id 'secret-cert'"),
    ("Cut open critical misconfigurations from 900 to 40 in a quarter", "cspm-rollout star.result"),
    ("Rolled out CSPM across 4,200 accounts", "cspm-rollout resume_bullets"),
])
def test_find_leaks_variants(bank: Path, text: str, leak: str):
    assert leak in find_leaks(validate(bank), f"<p>{text}</p>")


def test_find_leaks_role_summary(bank: Path):
    summary = "Owned security architecture for the payments platform"
    write(bank, "data/roles/acme-architect.yaml", {**ROLE, "summary": summary})
    assert "role summary of 'acme-architect'" in find_leaks(validate(bank), f"<p>{summary}</p>")


def test_find_leaks_public_text_of_non_public_item(bank: Path):
    text = "Led the response to a major ransomware outbreak"
    write(bank, "data/accomplishments/acme-architect/acme-2022-private-incident.yaml", accomplishment(
        id="acme-2022-private-incident", visibility="resume", public_text=text))
    leaks = find_leaks(validate(bank), f"<p>{text}</p>")
    assert "acme-2022-private-incident public_text of a non-public item" in leaks


def test_short_phone_is_not_scanned(bank: Path):
    write(bank, "data/profile.yaml", {"name": "T", "contact": {"phone": "x1234"}})
    assert find_leaks(validate(bank), "<p>call 1234</p>") == []


def test_find_leaks_without_profile(bank: Path):
    (bank / "data/profile.yaml").unlink()
    b = validate(bank)
    assert b.profile is None
    assert find_leaks(b, "<p>see acme-2022-private-incident</p>") == ["non-public id 'acme-2022-private-incident'"]


def test_build_requires_profile(bank: Path):
    (bank / "data/profile.yaml").unlink()
    with pytest.raises(ValueError, match="profile.yaml"):
        _build(bank)


def test_public_location_equal_to_contact_location_is_fine(bank: Path):
    write(bank, "data/profile.yaml", {"name": "T", "location": "Denver, CO", "contact": {"location": "Denver, CO"}})
    assert find_leaks(validate(bank), "<p>Denver, CO</p>") == []


def test_anonymized_employer_is_guarded(bank: Path):
    write(bank, "data/roles/acme-architect.yaml", {**ROLE, "public_employer": "A fintech company"})
    page = _build(bank)
    assert "A fintech company" in page
    assert ">Acme<" not in page
    assert "anonymized employer of role 'acme-architect'" in find_leaks(validate(bank), "<p>worked at Acme</p>")


def test_public_skills_override(bank: Path):
    path = "data/accomplishments/acme-architect/cspm-rollout.yaml"
    write(bank, path, accomplishment(visibility="public", public_text=PUBLIC_TEXT,
                                     skills=["CSPM", "Acme Internal Scanner"], public_skills=["CSPM"]))
    page = _build(bank)
    assert "Acme Internal Scanner" not in page
    assert 'data-skills="cspm"' in page

    write(bank, path, accomplishment(skills=["CSPM"], public_skills=["CSPM", "Zero Trust"]))
    assert any("public_skills must be a subset" in i.message for i in validate(bank).errors)


def test_refuses_to_clear_unrelated_folder(bank: Path):
    out = bank / "notasite"
    write(bank, "notasite/keep.txt", "important")
    with pytest.raises(FileExistsError):
        build_site(validate(bank), out, "https://example.test/", pdf=False)
    assert (out / "keep.txt").is_file()


def test_site_diff_lists_newly_public(bank: Path):
    def git(*args):
        subprocess.run(["git", "-C", str(bank), *args], check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-qm", "base")
    write(bank, "data/accomplishments/acme-architect/acme-2022-private-incident.yaml", accomplishment(
        id="acme-2022-private-incident", visibility="public", public_text="Led incident response for a major outage"))
    changes = {(c.kind, c.what) for c in public_diff(validate(bank), "HEAD")}
    assert changes == {("added", "accomplishment acme-2022-private-incident")}

    write(bank, "data/roles/acme-architect.yaml", {**ROLE, "public_employer": "A fintech company"})
    (bank / "data/education.yaml").unlink()
    changes = {(c.kind, c.what) for c in public_diff(validate(bank), "HEAD")}
    assert ("added", "role acme-architect employer") in changes
    assert ("removed", "education State U") in changes


def test_site_diff_outside_git_fails(bank: Path):
    with pytest.raises(RuntimeError, match="git archive HEAD failed"):
        public_diff(validate(bank), "HEAD")


# --- PDF resume ---------------------------------------------------------------


def _fake_pdf(lines: list[str], out: Path) -> Path:
    """A minimal one-page text PDF, so the PDF leak scan is tested without LibreOffice (CI has none)."""
    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")

    ops = "BT /F1 9 Tf 11 TL 36 760 Td " + " ".join(f"({esc(line)}) Tj T*" for line in lines) + " ET"
    stream = ops.encode("cp1252", errors="replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    data, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(data))
        data += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    data += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    data += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    out.write_bytes(bytes(data))
    return out


@pytest.fixture
def fake_soffice(monkeypatch):
    """Render the public resume with _fake_pdf instead of LibreOffice. Returns the extra lines to inject."""
    import resume_mgmt.site as site

    extra: list[str] = []
    monkeypatch.setattr(site, "require_soffice", lambda: "soffice")
    monkeypatch.setattr(site, "render_resume_pdf", lambda content, out: _fake_pdf([*content.lines(), *extra], out))
    return extra


def _pdf_text(path: Path) -> str:
    from resume_mgmt.site import output_text

    return " ".join(output_text(path).split())


def test_pdf_resume_is_public_only_and_linked(bank: Path, fake_soffice):
    out = bank / "build" / "site"
    build_site(validate(bank), out, "https://example.test/")
    pdf = out / "Test-Person-Resume.pdf"
    assert pdf.is_file()
    assert 'href="Test-Person-Resume.pdf"' in (out / "index.html").read_text(encoding="utf-8")

    text = _pdf_text(pdf)
    for expected in ["Test Person", "Security Architect", PUBLIC_TEXT, "Security architect focused on cloud and AI.",
                     "Remote, US | github.com/test", "CISSP, ISC2, Sep 2021", "BS | State U", "Cloud Security: CSPM"]:
        assert expected in text
    for absent in ["test@example.com", "555", "Denver", "4,200", "ransomware", "Internal Red Badge Program"]:
        assert absent not in text


def test_leak_guard_scans_the_pdf(bank: Path, fake_soffice):
    """Private data only in the PDF (not the HTML) must still fail the build and delete the output."""
    fake_soffice += ["Contact: test@example.com | (555) 010-0123", "Rolled out CSPM across 4,200 accounts"]
    with pytest.raises(SiteLeakError) as exc:
        build_site(validate(bank), bank / "build" / "site", "https://example.test/")
    leaks = "\n".join(exc.value.leaks)
    assert "profile.contact.email" in leaks
    assert "profile.contact.phone" in leaks
    assert "cspm-rollout resume_bullets" in leaks
    assert not (bank / "build/site").exists()


def test_missing_libreoffice_fails_before_clearing(bank: Path, monkeypatch):
    import resume_mgmt.site as site
    from resume_mgmt.render_pdf import SofficeNotFound

    out = bank / "build" / "site"
    build_site(validate(bank), out, "https://example.test/", pdf=False)

    def missing():
        raise SofficeNotFound("no soffice")

    monkeypatch.setattr(site, "require_soffice", missing)
    with pytest.raises(SofficeNotFound):
        build_site(validate(bank), out, "https://example.test/")
    assert (out / "index.html").is_file()
    assert not list(out.glob("*.pdf"))


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice not installed")
def test_real_pdf_resume(bank: Path):
    out = bank / "build" / "site"
    build_site(validate(bank), out, "https://example.test/")
    text = _pdf_text(out / "Test-Person-Resume.pdf")
    assert PUBLIC_TEXT in text
    assert "github.com/test" in text
    for absent in ["test@example.com", "010-0123", "Denver", "4,200", "ransomware"]:
        assert absent not in text
    assert not list(out.glob("*.docx"))


def test_bank_overlay_adds_pages(bank: Path):
    page = _build(bank)
    assert "how-it-works.html" not in page
    (bank / "site").mkdir()
    (bank / "site" / "how-it-works.html.j2").write_text("<p>About {{ name }}</p>", encoding="utf-8")
    page = _build(bank)
    assert 'href="how-it-works.html"' in page
    assert "About" in (bank / "build" / "site" / "how-it-works.html").read_text(encoding="utf-8")


def test_capabilities_page_groups_public_items_by_domain(bank: Path):
    write(bank, "data/roles/acme-architect.yaml", {**ROLE, "public_employer": "A retailer"})
    write(bank, "data/accomplishments/acme-architect/acme-2022-ai-review.yaml", accomplishment(
        id="acme-2022-ai-review", visibility="public", public_text="Reviewed every AI feature before launch",
        domains=["ai-security", "cloud-security"], strength=5, period={"start": "2022-01", "end": "2022-06"},
    ))
    index = _build(bank)
    page = (bank / "build/site/capabilities.html").read_text(encoding="utf-8")
    assert 'href="capabilities.html"' in index and 'href="./" aria-current="page"' in index
    assert '<a href="./#experience">experience</a>' in page  # same header bar as the role view
    # Most-evidenced domain first; a multi-domain item is listed under each domain and links to the others.
    assert page.index('id="cap-cloud-security"') < page.index('id="cap-ai-security"')
    assert page.count("Reviewed every AI feature before launch") == 2
    assert 'class="pill d-ai-security" href="#cap-ai-security"' in page
    cloud = page[page.index('id="cap-cloud-security"'):page.index('id="cap-ai-security"')]
    assert cloud.index("Reviewed every AI feature") < cloud.index(PUBLIC_TEXT)  # strongest first
    assert "Security Architect · A retailer" in page
    assert "Acme" not in page
    for absent in ["ransomware", "4,200", "acme-2022-private-incident", "test@example.com"]:
        assert absent not in page
    assert 'id="cap-grc"' not in page  # no public evidence


def test_leak_guard_covers_capabilities_page(bank: Path, monkeypatch):
    import resume_mgmt.site as site

    real = site.site_context

    def leaky(bank_, base_url, today=None):
        ctx = real(bank_, base_url, today)
        # Only capabilities.html gets the private text.
        ctx["capabilities"][0]["evidence"][0]["text"] = bank_.accomplishments["acme-2022-private-incident"].resume_bullets[0]
        return ctx

    monkeypatch.setattr(site, "site_context", leaky)
    with pytest.raises(SiteLeakError) as exc:
        _build(bank)
    assert "acme-2022-private-incident resume_bullets" in exc.value.leaks
    assert not (bank / "build/site").exists()


def _layer_boxes(page: str) -> dict[str, str]:
    """Skills map boxes by label, each box's HTML."""
    section = page[page.index('<section id="skills"'):]
    section = section[:section.index("</section>")]
    boxes = section.split('class="am-box"')[1:]
    return {re.search(r'<h3 class="am-label">([^<]+)</h3>', b).group(1): b for b in boxes}


def test_skills_map_places_skills_on_layers(bank: Path):
    write(bank, "data/skills.yaml", {"categories": [
        {"name": "Cloud Security", "layer": "cloud", "skills": [
            {"name": "CSPM", "aliases": ["cloud security posture management"]},
            {"name": "Zero Trust", "layer": "identity"},  # a skill's layer overrides its category's
        ]},
        {"name": "Tools", "skills": [{"name": "Jira"}]},  # no layer anywhere
    ]})
    write(bank, "data/accomplishments/acme-architect/acme-2022-zero-trust.yaml", accomplishment(
        id="acme-2022-zero-trust", visibility="public", public_text="Moved every contractor onto zero trust access",
        skills=["Zero Trust", "Jira"], strength=5,
    ))
    page = _build(bank)
    boxes = _layer_boxes(page)
    assert list(boxes) == ["Identity &amp; Access", "Cloud &amp; Infrastructure", "Other"]  # empty layers aren't drawn
    assert ">CSPM</button>" in boxes["Cloud &amp; Infrastructure"]
    assert ">Zero Trust</button>" in boxes["Identity &amp; Access"]
    assert ">Jira</button>" in boxes["Other"]
    # Each chip drives the skill filter and carries its proof line; no counts anywhere in the map.
    assert (f'data-kind="skill" data-value="cspm" data-proof="{PUBLIC_TEXT}" '
            'data-context="Security Architect · Acme"') in page
    assert 'data-value="jira" data-proof="Moved every contractor onto zero trust access"' in page
    assert '<span class="count">3 skills</span>' in page
    assert "matrix" not in page
    assert '<a href="#skills">skills</a>' in page


def test_skills_map_without_public_skills(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(
        visibility="public", public_text=PUBLIC_TEXT, skills=[],
    ))
    page = _build(bank)
    assert 'id="skills"' not in page and 'href="#skills"' not in page


def _public(bank: Path, n: int) -> None:
    for i in range(n):
        write(bank, f"data/accomplishments/acme-architect/extra-{i}.yaml", accomplishment(
            id=f"extra-{i}", visibility="public", public_text=f"Extra public highlight number {i}",
        ))


@pytest.mark.parametrize("public, toggle", [(5, None), (6, "show 2 more"), (9, "show 5 more")])
def test_long_roles_fold_behind_a_toggle(bank: Path, public: int, toggle: str | None):
    _public(bank, public - 1)  # the fixture already has one public item
    page = _build(bank)
    assert page.count('class="item"') == public  # every item is in the page for no-JS and print
    if toggle is None:  # one hidden item isn't worth a toggle
        assert "role-more" not in page and "data-preview" not in page
    else:
        assert 'data-preview="4"' in page
        assert f'aria-expanded="false" data-more="{toggle}">{toggle}</button>' in page
