"""Find weak spots in the bank. Feeds `/interview gaps`.

Each gap has a priority so the interview can work through the most valuable
ones first. Higher priority = ask sooner.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date

from .load import Bank
from .models import Accomplishment

STRONG = 3  # minimum strength that counts as solid evidence
MIN_ITEMS_PER_ROLE = 3
CHECKIN_EVERY_DAYS = 90
REVIEW_EVERY_DAYS = 365

# Skill categories in data/skills.yaml that map to each target domain.
DOMAIN_CATEGORIES = {
    "security-architecture": "Security Architecture",
    "cloud-security": "Cloud Security",
    "ai-security": "AI Security",
}


@dataclass
class Gap:
    kind: str
    target: str
    detail: str
    priority: int

    def to_dict(self) -> dict:
        return asdict(self)


def _months(ym: str) -> int:
    y, m = ym.split("-")
    return int(y) * 12 + int(m)


def _has_result(acc: Accomplishment) -> bool:
    return bool(acc.star.result) or bool(acc.metrics)


def _domain_coverage(bank: Bank, gaps: list[Gap]) -> None:
    targets = bank.profile.target_domains if bank.profile else list(DOMAIN_CATEGORIES)
    for domain in targets:
        strong = [a.id for a in bank.accomplishments.values() if domain in a.domains and (a.strength or 0) >= STRONG]
        if len(strong) < 5:
            gaps.append(Gap(
                "domain-coverage", domain,
                f"only {len(strong)} accomplishments with strength >= {STRONG} tagged '{domain}'"
                + (f" ({', '.join(strong)})" if strong else ""),
                100 - 10 * len(strong),
            ))


def _unevidenced_skills(bank: Bank, gaps: list[Gap]) -> None:
    if not bank.skills:
        return
    used = {s.lower() for a in bank.accomplishments.values() for s in a.skills}
    used |= {f.lower() for a in bank.accomplishments.values() for f in a.frameworks}
    targets = bank.profile.target_domains if bank.profile else list(DOMAIN_CATEGORIES)
    for domain in targets:
        category = DOMAIN_CATEGORIES.get(domain)
        cat = next((c for c in bank.skills.categories if c.name == category), None)
        if cat is None:
            continue
        missing = [s.name for s in cat.skills if s.name.lower() not in used]
        if missing:
            gaps.append(Gap(
                "unevidenced-skills", domain,
                f"no accomplishment shows: {', '.join(missing)}",
                45,
            ))


def _roles(bank: Bank, gaps: list[Gap]) -> None:
    for role in bank.roles.values():
        if role.track != "security":
            continue
        items = [a for a in bank.accomplishments.values() if a.role_id == role.id]
        strong = [a for a in items if (a.strength or 0) >= STRONG and _has_result(a)]
        if len(items) < MIN_ITEMS_PER_ROLE:
            gaps.append(Gap("thin-role", role.id, f"{len(items)} accomplishments", 65))
        elif not strong:
            gaps.append(Gap("thin-role", role.id, "no strong accomplishment with a stated result", 60))


def _employment_gaps(bank: Bank, gaps: list[Gap]) -> None:
    roles = sorted((r for r in bank.roles.values() if r.track == "security"), key=lambda r: r.period.start)
    for prev, nxt in zip(roles, roles[1:]):
        if prev.period.end in (None, "present"):
            continue
        gap = _months(nxt.period.start) - _months(prev.period.end)
        if gap > 2:
            gaps.append(Gap(
                "employment-gap", f"{prev.id} -> {nxt.id}",
                f"{gap - 1} months between {prev.period.end} and {nxt.period.start}",
                50,
            ))


def _recency_bonus(bank: Bank, role_id: str, today: date) -> int:
    """+10 for the current role, +5 for roles that ended in the last 3 years."""
    role = bank.roles[role_id]
    if role.period.end in (None, "present"):
        return 10
    months_ago = today.year * 12 + today.month - _months(role.period.end)
    return 5 if months_ago <= 36 else 0


def _items(bank: Bank, gaps: list[Gap], today: date) -> None:
    security_roles = {r.id for r in bank.roles.values() if r.track == "security"}
    never_reviewed = 0
    for acc in sorted(bank.accomplishments.values(), key=lambda a: -(a.strength or 0)):
        if acc.role_id not in security_roles:
            continue
        s = (acc.strength or 1) + _recency_bonus(bank, acc.role_id, today) // 5
        if not _has_result(acc):
            gaps.append(Gap("missing-result", acc.id, "no result or metric", 40 + 5 * s))
        elif not acc.metrics:
            gaps.append(Gap("no-metric", acc.id, "has a result but nothing measurable", 30 + 5 * s))
        unverified = [m for m in acc.metrics if not m.verified]
        if unverified:
            gaps.append(Gap(
                "unverified-metric", acc.id,
                "; ".join(f"{m.value} {m.unit} {m.description}" for m in unverified),
                20 + 3 * s,
            ))
        if acc.last_reviewed is None:
            never_reviewed += 1
        elif (today - acc.last_reviewed).days > REVIEW_EVERY_DAYS:
            gaps.append(Gap("stale", acc.id, f"last reviewed {acc.last_reviewed}", 15 + s))
    if never_reviewed:
        gaps.append(Gap("unreviewed", "bank", f"{never_reviewed} accomplishments never confirmed by the owner", 10))


CHECKIN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-checkin\.md$")


def last_checkin(bank: Bank) -> date | None:
    folder = bank.root / "interviews"
    dates = [
        date.fromisoformat(m.group(1))
        for p in folder.glob("*.md") if (m := CHECKIN_RE.match(p.name))
    ] if folder.is_dir() else []
    return max(dates, default=None)


def _checkin(bank: Bank, gaps: list[Gap], today: date) -> None:
    last = last_checkin(bank)
    if last is None:
        gaps.append(Gap("checkin-due", "interviews", "no check-in interview yet", 70))
    elif (today - last).days > CHECKIN_EVERY_DAYS:
        gaps.append(Gap("checkin-due", "interviews", f"last check-in {last} ({(today - last).days} days ago)", 70))


def find_gaps(bank: Bank, today: date | None = None) -> list[Gap]:
    today = today or date.today()
    gaps: list[Gap] = []
    _domain_coverage(bank, gaps)
    _unevidenced_skills(bank, gaps)
    _roles(bank, gaps)
    _employment_gaps(bank, gaps)
    _items(bank, gaps, today)
    _checkin(bank, gaps, today)
    return sorted(gaps, key=lambda g: (-g.priority, g.kind, g.target))
