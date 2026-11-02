from datetime import date
from pathlib import Path

import pytest

from resume_mgmt.gaps import find_gaps
from resume_mgmt.validate import validate

from test_validate import ROLE, accomplishment, write

TODAY = date(2026, 10, 30)


@pytest.fixture
def bank(tmp_path: Path) -> Path:
    write(tmp_path, "sources/resumes/2023-resume.txt", "resume text")
    write(tmp_path, "data/profile.yaml", {"name": "Test Person", "target_domains": ["cloud-security", "ai-security"]})
    write(tmp_path, "data/skills.yaml", {"categories": [
        {"name": "Cloud Security", "skills": [{"name": "CSPM"}, {"name": "CIEM"}]},
        {"name": "AI Security", "skills": [{"name": "LLM Security"}]},
    ]})
    write(tmp_path, "data/roles/acme-architect.yaml", ROLE)
    return tmp_path


def gaps_by_kind(root: Path) -> dict[str, list]:
    b = validate(root)
    assert b.errors == []
    out: dict[str, list] = {}
    for g in find_gaps(b, TODAY):
        out.setdefault(g.kind, []).append(g)
    return out


def test_domain_coverage_counts_only_strong_items(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml",
          accomplishment(domains=["cloud-security"], strength=4, skills=["CSPM"]))
    gaps = {g.target: g for g in gaps_by_kind(bank)["domain-coverage"]}
    assert gaps["ai-security"].priority == 100
    assert gaps["cloud-security"].priority == 90
    assert "cspm-rollout" in gaps["cloud-security"].detail


def test_unevidenced_skills_per_target_domain(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(skills=["CSPM"]))
    details = {g.target: g.detail for g in gaps_by_kind(bank)["unevidenced-skills"]}
    assert details["cloud-security"] == "no accomplishment shows: CIEM"
    assert "LLM Security" in details["ai-security"]


def test_missing_result_vs_no_metric_vs_unverified(bank: Path):
    write(bank, "data/accomplishments/acme-architect/a.yaml", accomplishment(id="a", strength=3))
    write(bank, "data/accomplishments/acme-architect/b.yaml",
          accomplishment(id="b", star={"result": "Faster remediation"}))
    write(bank, "data/accomplishments/acme-architect/c.yaml",
          accomplishment(id="c", metrics=[{"value": 70, "unit": "%", "description": "faster"}]))
    kinds = gaps_by_kind(bank)
    assert [g.target for g in kinds["missing-result"]] == ["a"]
    assert [g.target for g in kinds["no-metric"]] == ["b"]
    assert [g.target for g in kinds["unverified-metric"]] == ["c"]
    assert kinds["unreviewed"][0].detail.startswith("3 ")


def test_verified_and_reviewed_items_have_no_item_gaps(bank: Path):
    write(bank, "data/accomplishments/acme-architect/a.yaml", accomplishment(
        id="a", last_reviewed="2026-10-01",
        metrics=[{"value": 70, "unit": "%", "description": "faster", "verified": True}]))
    kinds = gaps_by_kind(bank)
    for kind in ("missing-result", "no-metric", "unverified-metric", "unreviewed", "stale"):
        assert kind not in kinds


def test_stale_review(bank: Path):
    write(bank, "data/accomplishments/acme-architect/a.yaml", accomplishment(
        id="a", last_reviewed="2024-01-01", star={"result": "done"}))
    assert [g.target for g in gaps_by_kind(bank)["stale"]] == ["a"]


def test_thin_role_and_other_track_ignored(bank: Path):
    write(bank, "data/roles/shop-clerk.yaml", {
        "id": "shop-clerk", "employer": "Shop", "title": "Clerk", "track": "other",
        "period": {"start": "2015-01", "end": "2016-01"}})
    write(bank, "data/accomplishments/shop-clerk/sales.yaml", accomplishment(id="sales", role_id="shop-clerk", period=None))
    kinds = gaps_by_kind(bank)
    assert [g.target for g in kinds["thin-role"]] == ["acme-architect"]
    assert all(g.target != "sales" for gs in kinds.values() for g in gs)


def test_employment_gap(bank: Path):
    write(bank, "data/roles/beta-engineer.yaml", {
        "id": "beta-engineer", "employer": "Beta", "title": "Engineer",
        "period": {"start": "2024-01", "end": "present"}})
    gap = gaps_by_kind(bank)["employment-gap"][0]
    assert gap.target == "acme-architect -> beta-engineer"
    assert gap.detail.startswith("6 months")


def test_checkin_due_then_recent(bank: Path):
    assert gaps_by_kind(bank)["checkin-due"][0].detail == "no check-in interview yet"
    write(bank, "interviews/2026-10-01-checkin.md", "# check-in")
    assert "checkin-due" not in gaps_by_kind(bank)
    (bank / "interviews/2026-10-01-checkin.md").rename(bank / "interviews/2026-05-01-checkin.md")
    assert "182 days ago" in gaps_by_kind(bank)["checkin-due"][0].detail


def test_current_role_ranks_above_old_role(bank: Path):
    write(bank, "data/roles/beta-engineer.yaml", {
        "id": "beta-engineer", "employer": "Beta", "title": "Engineer",
        "period": {"start": "2024-01", "end": "present"}})
    write(bank, "data/accomplishments/acme-architect/old.yaml", accomplishment(id="old", period=None, strength=2))
    write(bank, "data/accomplishments/beta-engineer/new.yaml",
          accomplishment(id="new", role_id="beta-engineer", period=None, strength=2))
    ranked = [g.target for g in gaps_by_kind(bank)["missing-result"]]
    assert ranked == ["new", "old"]


def test_unevidenced_skills_skips_missing_taxonomy_and_categories(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment())
    write(bank, "data/skills.yaml", {"categories": [{"name": "Cloud Security", "skills": [{"name": "CIEM"}]}]})
    assert [g.target for g in gaps_by_kind(bank)["unevidenced-skills"]] == ["cloud-security"]  # no AI Security category
    (bank / "data/skills.yaml").unlink()
    assert "unevidenced-skills" not in gaps_by_kind(bank)


def test_current_role_is_not_an_employment_gap(bank: Path):
    write(bank, "data/roles/acme-architect.yaml", {**ROLE, "period": {"start": "2020-01", "end": "present"}})
    write(bank, "data/roles/beta-engineer.yaml", {**ROLE, "id": "beta-engineer", "period": {"start": "2024-01", "end": "present"}})
    assert "employment-gap" not in gaps_by_kind(bank)
