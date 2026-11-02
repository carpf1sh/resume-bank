import json
from pathlib import Path

import pytest
import yaml

from resume_mgmt.models import EXPORTED_SCHEMAS
from resume_mgmt.validate import validate

REPO = Path(__file__).resolve().parents[1]


def write(root: Path, rel: str, data) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


ROLE = {
    "id": "acme-architect",
    "employer": "Acme",
    "title": "Security Architect",
    "period": {"start": "2020-01", "end": "2023-06"},
}


def accomplishment(**overrides):
    acc = {
        "id": "cspm-rollout",
        "role_id": "acme-architect",
        "title": "CSPM rollout",
        "period": {"start": "2021-03", "end": "2021-11"},
        "visibility": "resume",
        "resume_bullets": ["Rolled out CSPM across 4,200 accounts"],
        "sources": ["sources/resumes/2023-resume.txt"],
    }
    acc.update(overrides)
    return acc


@pytest.fixture
def bank(tmp_path: Path) -> Path:
    write(tmp_path, "sources/resumes/2023-resume.txt", "resume text")
    write(tmp_path, "data/profile.yaml", {"name": "Test Person"})
    write(tmp_path, "data/certifications.yaml", {"certifications": []})
    write(tmp_path, "data/education.yaml", {"education": []})
    write(tmp_path, "data/skills.yaml", {"categories": []})
    write(tmp_path, "data/roles/acme-architect.yaml", ROLE)
    write(tmp_path, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment())
    return tmp_path


def messages(root: Path) -> list[str]:
    return [i.message for i in validate(root).errors]


def test_valid_bank_passes(bank: Path):
    result = validate(bank)
    assert result.errors == []
    assert result.warnings == []
    assert "cspm-rollout" in result.accomplishments


def test_public_requires_public_text(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(visibility="public"))
    assert any("requires public_text" in m for m in messages(bank))


def test_unknown_role_id(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(role_id="nope"))
    errs = messages(bank)
    assert any("unknown role_id 'nope'" in m for m in errs)


def test_period_outside_role(bank: Path):
    acc = accomplishment(period={"start": "2019-01", "end": "2019-06"})
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", acc)
    assert any("outside role" in m for m in messages(bank))


def test_end_before_start(bank: Path):
    acc = accomplishment(period={"start": "2022-05", "end": "2021-01"})
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", acc)
    assert any("before start" in m for m in messages(bank))


def test_missing_source_file(bank: Path):
    acc = accomplishment(sources=["sources/resumes/missing.docx"])
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", acc)
    assert any("source not found" in m for m in messages(bank))


def test_sources_required(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(sources=[]))
    assert any(m.startswith("sources:") for m in messages(bank))


def test_metric_needs_description(bank: Path):
    acc = accomplishment(metrics=[{"value": 78, "unit": "%"}])
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", acc)
    assert any("description" in m for m in messages(bank))


def test_unknown_keys_rejected(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(resut="typo"))
    assert any("resut" in m for m in messages(bank))


def test_duplicate_id(bank: Path):
    write(bank, "data/accomplishments/acme-architect/copy.yaml", accomplishment())
    assert any("duplicate id" in m for m in messages(bank))


def test_file_must_match_id_and_role(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(id="other-name"))
    assert any("must live at" in m for m in messages(bank))


def test_unknown_skill_is_warning(bank: Path):
    write(bank, "data/skills.yaml", {"categories": [{"name": "Cloud", "skills": [{"name": "CSPM"}]}]})
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(skills=["cspm", "Basket Weaving"]))
    result = validate(bank)
    assert result.errors == []
    assert any("Basket Weaving" in w.message for w in result.warnings)


def tailored(bank: Path, bullet_sources: list[str]) -> None:
    write(bank, "applications/2026-11-01-acme-architect/posting.md", "posting")
    write(
        bank,
        "applications/2026-11-01-acme-architect/resume.yaml",
        {
            "posting": "posting.md",
            "summary": "Security architect.",
            "roles": [
                {
                    "role_id": "acme-architect",
                    "bullets": [{"text": "Rolled out CSPM", "sources": bullet_sources}],
                }
            ],
        },
    )


def test_tailored_resume_valid(bank: Path):
    tailored(bank, ["cspm-rollout"])
    assert messages(bank) == []


def test_tailored_bullet_must_cite(bank: Path):
    tailored(bank, [])
    assert any("sources" in m for m in messages(bank))


def test_tailored_cannot_cite_private(bank: Path):
    write(bank, "data/accomplishments/acme-architect/cspm-rollout.yaml", accomplishment(visibility="private"))
    tailored(bank, ["cspm-rollout"])
    assert any("private accomplishment" in m for m in messages(bank))


def test_tailored_cannot_cite_unknown(bank: Path):
    tailored(bank, ["made-up"])
    assert any("unknown accomplishment 'made-up'" in m for m in messages(bank))


def test_invalid_yaml(bank: Path):
    write(bank, "data/roles/acme-architect.yaml", "id: [unclosed")
    assert any(m.startswith("invalid YAML") for m in messages(bank))


def test_empty_file(bank: Path):
    write(bank, "data/roles/acme-architect.yaml", "")
    assert "file is empty" in messages(bank)


def test_missing_singleton_is_warning(bank: Path):
    (bank / "data/skills.yaml").unlink()
    result = validate(bank)
    assert result.errors == []
    assert [str(w) for w in result.warnings] == ["data/skills.yaml: not found (create it during /ingest)"]


def test_role_file_must_match_id(bank: Path):
    (bank / "data/roles/acme-architect.yaml").unlink()
    write(bank, "data/roles/acme.yaml", ROLE)
    assert "file name must match id 'acme-architect'" in messages(bank)


def test_duplicate_certification_id(bank: Path):
    cert = {"id": "cissp", "name": "CISSP", "issuer": "ISC2"}
    write(bank, "data/certifications.yaml", {"certifications": [cert, cert]})
    assert any("duplicate id 'cissp'" in m for m in messages(bank))


def test_certification_id_clashes_with_accomplishment(bank: Path):
    write(bank, "data/certifications.yaml", {"certifications": [{"id": "cspm-rollout", "name": "X", "issuer": "Y"}]})
    assert any("duplicate id 'cspm-rollout'" in m for m in messages(bank))


def tailored_with(bank: Path, **overrides) -> None:
    tailored(bank, ["cspm-rollout"])
    path = bank / "applications/2026-11-01-acme-architect/resume.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.update(overrides)
    write(bank, "applications/2026-11-01-acme-architect/resume.yaml", data)


@pytest.mark.parametrize("overrides, error", [
    ({"posting": "missing.md"}, "posting not found: missing.md"),
    ({"roles": [{"role_id": "nope"}]}, "unknown role_id 'nope'"),
    ({"certifications": ["nope"]}, "unknown certification 'nope'"),
    ({"certifications": ["secret-cert"]}, "private certification 'secret-cert'"),
])
def test_tailored_resume_reference_errors(bank: Path, overrides: dict, error: str):
    write(bank, "data/certifications.yaml", {"certifications": [
        {"id": "secret-cert", "name": "Secret", "issuer": "Acme", "visibility": "private"}]})
    tailored_with(bank, **overrides)
    assert error in messages(bank)


def test_tailored_bullet_must_cite_same_role(bank: Path):
    write(bank, "data/roles/beta-engineer.yaml", {**ROLE, "id": "beta-engineer", "employer": "Beta"})
    tailored_with(bank, roles=[{"role_id": "beta-engineer", "bullets": [{"text": "x", "sources": ["cspm-rollout"]}]}])
    assert "bullet under 'beta-engineer' cites 'cspm-rollout' from 'acme-architect'" in messages(bank)


def test_tailored_unknown_skill_is_warning(bank: Path):
    write(bank, "data/skills.yaml", {"categories": [{"name": "Cloud", "skills": [{"name": "CSPM"}]}]})
    tailored_with(bank, skills=["cspm", "Basket Weaving"])
    result = validate(bank)
    assert result.errors == []
    assert [w.message for w in result.warnings if w.path.endswith("resume.yaml")] == [
        "skills not in data/skills.yaml: Basket Weaving"
    ]


def test_status_history_out_of_order_warns(bank: Path):
    tailored(bank, ["cspm-rollout"])
    write(bank, "applications/2026-11-01-acme-architect/status.yaml", {
        "company": "Acme", "title": "X", "created": "2026-11-01", "stage": "applied",
        "history": [{"date": "2026-11-05", "stage": "drafted"}, {"date": "2026-11-02", "stage": "applied"}],
    })
    assert [w.message for w in validate(bank).warnings] == ["history is not in date order"]


@pytest.mark.parametrize("stem", EXPORTED_SCHEMAS)
def test_exported_schemas_are_current(stem: str):
    path = REPO / "schemas" / f"{stem}.schema.json"
    assert json.loads(path.read_text(encoding="utf-8")) == EXPORTED_SCHEMAS[stem].model_json_schema(), (
        "schemas/ is stale: run `uv run rmgr schema`"
    )
