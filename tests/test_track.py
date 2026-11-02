import json
import re
from datetime import date
from pathlib import Path

import pytest

from resume_mgmt.models import Certification
from resume_mgmt.site import build_site, public_resume_content, site_context
from resume_mgmt.track import career_track, short_cert, short_degree, short_employer
from resume_mgmt.validate import validate

from test_validate import ROLE, write

TODAY = date(2026, 11, 1)


@pytest.mark.parametrize("name, short", [
    ("Woodgrove (Woodgrove Financial Services)", "Woodgrove"),
    ("Northwind Corporation", "Northwind"),
    ("Acme, Inc.", "Acme"),
    ("Tailspin Group", "Tailspin Group"),
    ("A regional bank", "A regional bank"),
])
def test_short_employer(name: str, short: str):
    assert short_employer(name) == short


@pytest.mark.parametrize("degree, short", [
    ("Master of Science", "M.S."),
    ("Bachelor of Business Administration", "B.B.A."),
    ("BS", "BS"),
    ("MBA", "MBA"),
])
def test_short_degree(degree: str, short: str):
    assert short_degree(degree) == short


@pytest.mark.parametrize("cert, short", [
    ({"name": "Certified Information Systems Security Professional (CISSP)"}, "CISSP"),
    ({"name": "AWS Certified Security - Specialty", "short_name": "AWS Security"}, "AWS Security"),
    ({"name": "CompTIA Security+"}, "CompTIA Security+"),
])
def test_short_cert(cert: dict, short: str):
    assert short_cert(Certification(id="c", issuer="X", **cert)) == short


def test_lapsed_is_inclusive_of_expiry_month():
    cert = Certification(id="c", name="C", issuer="X", expires="2026-01")
    assert not cert.lapsed("2026-01")
    assert cert.lapsed("2026-02")
    assert not Certification(id="c", name="C", issuer="X").lapsed("2099-01")


@pytest.fixture
def bank(tmp_path: Path) -> Path:
    write(tmp_path, "data/profile.yaml", {"name": "Test Person", "headline": "Security Architect"})
    write(tmp_path, "data/roles/acme-architect.yaml", {
        **ROLE, "employer": "Acme Holdings", "public_employer": "A large retailer",
        "period": {"start": "2019-01", "end": "2022-06"},
    })
    write(tmp_path, "data/roles/beta-lead.yaml", {
        **ROLE, "id": "beta-lead", "employer": "Beta Corporation", "title": "Security Lead",
        "period": {"start": "2022-07", "end": "present"},
    })
    write(tmp_path, "data/roles/shop-clerk.yaml", {
        **ROLE, "id": "shop-clerk", "employer": "Corner Shop", "title": "Clerk", "track": "other",
        "period": {"start": "2012-01", "end": "2014-01"},
    })
    write(tmp_path, "data/education.yaml", {"education": [
        {"institution": "Night School", "degree": "Master of Science", "field": "Cybersecurity", "honors": "GPA 3.8",
         "period": {"start": "2020-09", "end": "2022-12"}},
        {"institution": "First College", "degree": "Bachelor of Arts", "period": {"start": "2013-09", "end": "2017-05"}},
    ]})
    write(tmp_path, "data/certifications.yaml", {"certifications": [
        {"id": "cissp", "name": "Certified Information Systems Security Professional (CISSP)", "issuer": "ISC2",
         "earned": "2020-05"},
        {"id": "gcih", "name": "GIAC Certified Incident Handler (GCIH)", "issuer": "GIAC", "earned": "2021-03",
         "expires": "2025-09"},
        {"id": "old-cert", "name": "Ancient Cert (ANC)", "issuer": "X", "earned": "2010-01", "expires": "2013-01"},
        {"id": "secret-cert", "name": "Internal Red Badge (IRB)", "issuer": "Acme", "earned": "2020-01",
         "visibility": "resume"},
    ]})
    assert validate(tmp_path).errors == []
    return tmp_path


def _svgs(root: Path) -> str:
    track = career_track(validate(root), TODAY)
    return str(track["wide"]) + str(track["narrow"])


def test_track_marks(bank: Path):
    svg = _svgs(bank)
    for drawing in ("tk-wide", "tk-narrow"):
        assert f'class="tk {drawing}"' in svg
    # roles: security track only, public employer, shortened corporate name
    assert "Security Lead · Beta Corporation" in svg and ">Beta<" in svg
    assert "A large retailer" in svg and "Acme Holdings" not in svg
    assert "Clerk" not in svg
    # degrees: the one that ended before the first security role is left off
    assert "Master of Science, Cybersecurity · Night School · GPA 3.8" in svg and ">M.S.<" in svg
    assert "First College" not in svg
    # certs: active, lapsed (ends in an x), lapsed before the track began, not public
    assert "Certified Information Systems Security Professional (CISSP) · ISC2 · active" in svg
    assert 'data-dates="since May 2020"' in svg
    assert "GIAC Certified Incident Handler (GCIH) · GIAC · lapsed" in svg
    assert 'data-dates="Mar 2021 – Sep 2025"' in svg
    assert svg.count('class="tk-x"') == 2  # one per drawing
    assert "Ancient" not in svg and "Red Badge" not in svg
    # the current role is where the detail line starts
    current = re.search(r'<a class="tk-hit tk-role tk-current"[^>]*data-detail="([^"]+)"', svg)
    assert current.group(1) == "Security Lead · Beta Corporation"


def test_track_marks_link_to_their_entries(bank: Path):
    out = bank / "build" / "site"
    build_site(validate(bank), out, "https://example.test/", pdf=False)
    page = (out / "index.html").read_text(encoding="utf-8")
    targets = set(re.findall(r'<a class="tk-hit[^"]*" href="#([^"]+)"', page))
    assert {"role-beta-corporation-security-lead", "cert-giac-certified-incident-handler-gcih",
            "degree-master-of-science-cybersecurity-night-school"} <= targets
    for target in targets:
        assert page.count(f'id="{target}"') == 1, target


def test_track_lanes_do_not_collide(bank: Path):
    """CISSP and GCIH overlap in time, so they need two lanes below the main line."""
    wide = str(career_track(validate(bank), TODAY)["wide"])
    lanes = {float(y) for y in re.findall(r'class="tk-diamond" x="[^"]+" y="([^"]+)"', wide)}
    assert len(lanes) == 2


def test_track_absent_without_security_roles(bank: Path):
    for name in ("acme-architect", "beta-lead"):
        (bank / f"data/roles/{name}.yaml").unlink()
    assert career_track(validate(bank), TODAY) is None
    page_ctx = site_context(validate(bank), "https://example.test/", TODAY)
    assert page_ctx["track"] is None


def test_lapsed_cert_on_site_but_not_in_json_ld_or_resume(bank: Path):
    loaded = validate(bank)
    ctx = site_context(loaded, "https://example.test/", TODAY)
    gsec = next(c for c in ctx["certifications"] if "GCIH" in c["name"])
    assert gsec["lapsed"] == "Sep 2025"
    assert next(c for c in ctx["certifications"] if "CISSP" in c["name"])["lapsed"] is None
    credentials = [c["name"] for c in json.loads(ctx["json_ld"])["hasCredential"]]
    assert any("CISSP" in n for n in credentials) and not any("GCIH" in n for n in credentials)
    resume_certs = public_resume_content(loaded, ctx).certifications
    assert any("CISSP" in line for line in resume_certs) and not any("GCIH" in line for line in resume_certs)


def test_cert_still_valid_in_its_expiry_month(bank: Path):
    ctx = site_context(validate(bank), "https://example.test/", date(2025, 9, 15))
    assert next(c for c in ctx["certifications"] if "GCIH" in c["name"])["lapsed"] is None
