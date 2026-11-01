"""Pydantic models for every file in the bank.

These models are the schema. JSON Schemas in `schemas/` are exported from
them with `rmgr schema`, so edit here, not there.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Visibility = Literal["public", "resume", "private"]

Domain = Literal[
    "security-architecture",
    "cloud-security",
    "ai-security",
    "appsec",
    "iam",
    "grc",
    "detection-response",
    "devsecops",
    "data-security",
    "network-security",
    "leadership",
]

Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
YearMonth = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2021-03"])]


class Strict(BaseModel):
    """Base model: unknown keys are errors, so typos never silently drop data."""

    model_config = ConfigDict(extra="forbid")


class Period(Strict):
    start: YearMonth
    end: YearMonth | Literal["present"] | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> Period:
        if self.end not in (None, "present") and self.end < self.start:
            raise ValueError(f"period end {self.end} is before start {self.start}")
        return self

    def end_or_max(self) -> str:
        return "9999-12" if self.end in (None, "present") else self.end

    def contains(self, other: Period) -> bool:
        return self.start <= other.start and other.end_or_max() <= self.end_or_max()


class Link(Strict):
    label: str
    url: str


# --- profile.yaml ---------------------------------------------------------


class Contact(Strict):
    """Private contact details: rendered on resumes, never on the public site."""

    email: str | None = None
    phone: str | None = None
    location: str | None = None


class Profile(Strict):
    name: str
    headline: str | None = None
    location: str | None = Field(None, description="Public location, e.g. 'Denver, CO' or 'Remote, US'")
    contact: Contact = Contact()
    links: list[Link] = Field(default_factory=list, description="Public links (LinkedIn, GitHub, ...)")
    target_roles: list[str] = Field(default_factory=list)
    target_domains: list[Domain] = Field(
        default_factory=lambda: ["security-architecture", "cloud-security", "ai-security"],
        description="Domains the gap report checks for strong evidence",
    )
    summaries: dict[Domain | Literal["general"], str] = Field(
        default_factory=dict, description="Professional summary per target domain"
    )
    public_summary: str | None = Field(None, description="Summary used on the public site")
    site_url: str | None = Field(None, description="Public URL of the portfolio site, for canonical/OG tags")


# --- skills.yaml ------------------------------------------------------------


class Skill(Strict):
    name: str
    aliases: list[str] = Field(default_factory=list)


class SkillCategory(Strict):
    name: str
    skills: list[Skill]


class SkillsTaxonomy(Strict):
    categories: list[SkillCategory]

    def all_names(self) -> set[str]:
        """Canonical names and aliases, lowercased."""
        names: set[str] = set()
        for cat in self.categories:
            for skill in cat.skills:
                names.add(skill.name.lower())
                names.update(a.lower() for a in skill.aliases)
        return names


# --- roles/<id>.yaml --------------------------------------------------------


class Role(Strict):
    id: Slug
    employer: str
    public_employer: str | None = Field(
        None, description="Name to show publicly if the employer must be anonymized"
    )
    title: str
    location: str | None = None
    employment_type: Literal["full-time", "part-time", "contract", "consulting", "internship"] = "full-time"
    track: Literal["security", "other"] = Field(
        "security", description="'other' = pre-security roles: kept for history, skipped by gap checks"
    )
    period: Period
    summary: str | None = Field(None, description="One or two lines on scope and mandate")
    team_size: int | None = None
    sources: list[str] = Field(default_factory=list)


# --- accomplishments/<role-id>/<id>.yaml -----------------------------------


class Star(Strict):
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None


class Metric(Strict):
    value: float | int
    unit: str
    description: str
    verified: bool = Field(False, description="True once the owner has confirmed the number")


class Leadership(Strict):
    team_size: int | None = None
    direct_reports: int | None = None
    cross_functional: bool | None = None


class Accomplishment(Strict):
    id: Slug
    role_id: Slug
    title: str
    period: Period | None = None
    star: Star = Star()
    metrics: list[Metric] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    domains: list[Domain] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    leadership: Leadership | None = None
    visibility: Visibility = "resume"
    public_text: str | None = Field(None, description="Sanitized wording for the public site")
    public_skills: list[str] | None = Field(
        None, description="Skills to tag on the public site when `skills` names something internal (default: skills)"
    )
    resume_bullets: list[str] = Field(default_factory=list)
    sources: list[str] = Field(min_length=1, description="Files this accomplishment was drawn from")
    strength: int | None = Field(None, ge=1, le=5)
    last_reviewed: date | None = None

    @model_validator(mode="after")
    def _public_needs_public_text(self) -> Accomplishment:
        if self.visibility == "public" and not self.public_text:
            raise ValueError("visibility 'public' requires public_text")
        return self


# --- certifications.yaml / education.yaml / projects/<id>.yaml -------------


class Certification(Strict):
    id: Slug
    name: str
    issuer: str
    earned: YearMonth | None = None
    expires: YearMonth | None = None
    credential_id: str | None = None
    verify_url: str | None = None
    visibility: Visibility = "public"


class Certifications(Strict):
    certifications: list[Certification] = Field(default_factory=list)


class Degree(Strict):
    institution: str
    degree: str
    field: str | None = None
    period: Period | None = None
    honors: str | None = Field(None, description="GPA, honors, distinctions")
    visibility: Visibility = "public"


class Education(Strict):
    education: list[Degree] = Field(default_factory=list)


class Project(Strict):
    id: Slug
    name: str
    url: str | None = None
    period: Period | None = None
    description: str
    skills: list[str] = Field(default_factory=list)
    domains: list[Domain] = Field(default_factory=list)
    visibility: Visibility = "public"
    public_text: str | None = None
    sources: list[str] = Field(default_factory=list)


# --- applications/<dir>/resume.yaml ----------------------------------------


class TailoredBullet(Strict):
    text: str
    sources: list[Slug] = Field(min_length=1, description="Accomplishment ids backing this bullet")


class TailoredRole(Strict):
    role_id: Slug
    condensed: bool = Field(False, description="Render title/dates only, no bullets")
    bullets: list[TailoredBullet] = Field(default_factory=list)


class TailoredResume(Strict):
    posting: str = Field(description="Path to the frozen posting, relative to the application folder")
    summary: str
    skills: list[str] = Field(default_factory=list)
    roles: list[TailoredRole]
    certifications: list[Slug] = Field(default_factory=list)
    projects: list[Slug] = Field(default_factory=list)
    include_education: bool = True


# --- applications/<dir>/posting.md frontmatter / status.yaml ----------------


class PostingMeta(Strict):
    """YAML frontmatter of a posting (jobs/inbox/*.md, applications/*/posting.md)."""

    id: Slug | None = None
    company: str
    title: str
    url: str | None = None
    location: str | None = None
    remote: bool | None = None
    source: str | None = Field(None, description="Where the posting came from: a URL, a file, a job board")
    found_at: date | None = None
    salary: str | None = None
    keywords: list[str] = Field(
        default_factory=list,
        description="Posting terms to check coverage for that data/skills.yaml doesn't already match",
    )
    match_hints: list[str] = Field(default_factory=list)


Stage = Literal["drafted", "applied", "screening", "interviewing", "offer", "rejected", "withdrawn", "closed"]


class StatusEvent(Strict):
    date: date
    stage: Stage
    note: str | None = None


class ApplicationStatus(Strict):
    company: str
    title: str
    url: str | None = None
    stage: Stage = "drafted"
    created: date
    history: list[StatusEvent] = Field(default_factory=list)
    notes: str | None = None


# Files whose schema is exported, keyed by schema file stem.
EXPORTED_SCHEMAS: dict[str, type[BaseModel]] = {
    "profile": Profile,
    "skills": SkillsTaxonomy,
    "role": Role,
    "accomplishment": Accomplishment,
    "certifications": Certifications,
    "education": Education,
    "project": Project,
    "tailored-resume": TailoredResume,
    "application-status": ApplicationStatus,
    "posting": PostingMeta,
}
