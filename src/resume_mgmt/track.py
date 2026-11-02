"""The career track: a git-style graphic of the security career, drawn as inline SVG.

Roles are commits on the main line, degrees are branches that merge back in, and
certifications are branches that stay open while active and end in an x once they
lapse. It covers the security track only: a degree or certification that ended
before the first security role is left off (it stays in its own section).

The same marks are drawn twice, across the page for wide screens and down it for
phones. Every mark carries its detail line for hover and focus (site.js), and links to
its entry further down the page through `anchor()`, which site.py uses for the entries' ids.
Only public items reach it, and roles show `public_employer` when one is set.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from html import escape

from markupsafe import Markup

from .load import Bank
from .models import Certification, Period
from .resume_doc import fmt_month, fmt_period

ROLE, DEGREE, CERT = "role", "degree", "cert"
CORP_SUFFIX = re.compile(r",?\s+(Corporation|Corp\.?|Incorporated|Inc\.?|LLC|Ltd\.?|Co\.)$", re.I)
CHAR_W = 6.6  # width of one 11px monospace character, for fitting labels
LANE_GAP = 0.25  # years between two branches sharing a lane


def anchor(kind: str, *parts: str | None) -> str:
    """The id of a role, degree or cert entry on the page, built only from public text."""
    return "-".join([kind, re.sub(r"[^a-z0-9]+", "-", " ".join(filter(None, parts)).lower()).strip("-")])


def years(ym: str) -> float:
    year, month = ym.split("-")
    return int(year) + (int(month) - 1) / 12


def short_employer(name: str) -> str:
    """'Woodgrove (Woodgrove Financial Services)' -> 'Woodgrove', 'Northwind Corporation' -> 'Northwind'."""
    name = re.sub(r"\s*\(.*?\)", "", name).strip()
    return CORP_SUFFIX.sub("", name) or name


def short_degree(degree: str) -> str:
    """'Master of Science' -> 'M.S.'. Names that are already short ('BS', 'MBA') stay as they are."""
    words = [w for w in degree.split() if w[0].isupper()]
    return ".".join(w[0] for w in words) + "." if len(words) > 1 else degree


def short_cert(cert: Certification) -> str:
    """`short_name`, else the acronym in trailing parentheses ('... (CISSP)'), else the name."""
    if cert.short_name:
        return cert.short_name
    if m := re.search(r"\(([A-Z0-9+-]{2,10})\)\s*$", cert.name):
        return m.group(1)
    return cert.name


@dataclass
class Mark:
    kind: str
    label: str  # drawn on the track; for roles, the short employer name
    detail: str
    dates: str
    start: float
    anchor: str
    end: float | None = None  # None: still open
    lapsed: bool = False
    lane: int = 0


def _end(period: Period) -> float | None:
    return None if period.end in (None, "present") else years(period.end)


def _marks(bank: Bank, month: str) -> tuple[list[Mark], list[Mark], list[Mark]] | None:
    roles = sorted((r for r in bank.roles.values() if r.track == "security"), key=lambda r: r.period.start)
    if not roles:
        return None
    begin = years(roles[0].period.start)
    role_marks = []
    for r in roles:
        employer = r.public_employer or r.employer
        role_marks.append(Mark(ROLE, short_employer(employer), f"{r.title} · {employer}", fmt_period(r.period),
                               years(r.period.start), anchor(ROLE, employer, r.title), _end(r.period)))
    degrees = []
    for d in bank.education.education:
        if d.visibility != "public" or d.period is None:
            continue
        end = _end(d.period)
        if end is not None and end < begin:
            continue
        name = f"{d.degree}, {d.field}" if d.field else d.degree
        degrees.append(Mark(DEGREE, short_degree(d.degree), " · ".join(filter(None, [name, d.institution, d.honors])),
                            fmt_period(d.period), max(years(d.period.start), begin),
                            anchor(DEGREE, d.degree, d.field, d.institution), end))
    certs = []
    for c in bank.certifications.certifications:
        if c.visibility != "public" or not c.earned:
            continue
        lapsed = c.lapsed(month)
        if lapsed and years(c.expires) < begin:
            continue
        dates = f"{fmt_month(c.earned)} – {fmt_month(c.expires)}" if lapsed else f"since {fmt_month(c.earned)}"
        certs.append(Mark(CERT, short_cert(c), f"{c.name} · {c.issuer} · {'lapsed' if lapsed else 'active'}", dates,
                          max(years(c.earned), begin), anchor(CERT, c.name), years(c.expires) if lapsed else None, lapsed))
    return role_marks, degrees, certs


def _assign_lanes(marks: list[Mark], now: float) -> int:
    """Greedy lanes: a branch takes the first lane that is free when it starts."""
    free_at: list[float] = []
    for m in sorted(marks, key=lambda m: m.start):
        lane = next((i for i, t in enumerate(free_at) if t <= m.start), len(free_at))
        if lane == len(free_at):
            free_at.append(0)
        m.lane = lane
        free_at[lane] = (m.end or now) + LANE_GAP
    return len(free_at)


def _segments(roles: list[Mark], now: float) -> list[list]:
    """Consecutive roles at one employer merge into one labelled stretch: [label, start, end]."""
    segs: list[list] = []
    for m in roles:
        if segs and segs[-1][0] == m.label:
            segs[-1][2] = m.end or now
        else:
            segs.append([m.label, m.start, m.end or now])
    return segs


def _n(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _hit(m: Mark, shape: str, current: bool = False) -> str:
    """A mark linking to its entry on the page, with a detail line site.js shows; <title> is the no-JS tooltip."""
    label = f"{m.detail}, {m.dates}"
    cls = f"tk-hit tk-{m.kind}" + (" tk-current" if current else "")
    return (f'<a class="{cls}" href="#{m.anchor}" aria-label="{escape(label)}" data-detail="{escape(m.detail)}" '
            f'data-dates="{escape(m.dates)}"><title>{escape(label)}</title>{shape}</a>')


def _dot(x: float, y: float, cls: str, r: float = 5) -> str:
    return f'<circle class="{cls}" cx="{_n(x)}" cy="{_n(y)}" r="{r}"/>'


def _diamond(x: float, y: float) -> str:
    return (f'<rect class="tk-diamond" x="{_n(x - 5)}" y="{_n(y - 5)}" width="10" height="10" '
            f'transform="rotate(45 {_n(x)} {_n(y)})"/>')


def _cross(x: float, y: float) -> str:
    return f'<path class="tk-x" d="M{_n(x - 4)} {_n(y - 4)}l8 8m0 -8l-8 8"/>'


def _text(x: float, y: float, text: str, cls: str, anchor: str = "start") -> str:
    return f'<text class="{cls}" x="{_n(x)}" y="{_n(y)}" text-anchor="{anchor}">{escape(text)}</text>'


def _svg(cls: str, width: float, height: float, label: str, parts: list[str]) -> Markup:
    return Markup(f'<svg class="tk {cls}" viewBox="0 0 {_n(width)} {_n(height)}" role="group" '
                  f'aria-label="{escape(label)}">' + "".join(parts) + "</svg>")


class _Track:
    def __init__(self, roles: list[Mark], degrees: list[Mark], certs: list[Mark], now: float):
        self.roles, self.degrees, self.certs, self.now = roles, degrees, certs, now
        self.n_deg = _assign_lanes(degrees, now)
        self.n_cert = _assign_lanes(certs, now)
        self.lo = roles[0].start - 0.12
        self.hi = max(now, roles[0].start + 1) + 0.12
        self.segs = _segments(roles, now)
        last = roles[-1]
        self.main_end = now if last.end is None else last.end
        self.label = f"Career track, {math.floor(roles[0].start)} to {'now' if last.end is None else math.floor(last.end)}"

    def _role_hits(self, at) -> list[str]:
        return [_hit(m, _dot(*at(m.start), "tk-dot"), current=i == len(self.roles) - 1) for i, m in enumerate(self.roles)]

    def wide(self) -> Markup:
        W, P = 680, 20
        x = lambda t: P + (t - self.lo) / (self.hi - self.lo) * (W - 2 * P)
        M = 51 + 15 * (self.n_deg - 1) if self.n_deg else 24
        deg_y = lambda k: M - 30 - 15 * k
        cert_y = lambda k: M + 27 + 15 * k
        band = (cert_y(self.n_cert - 1) if self.n_cert else M) + 30
        out = [f'<path class="tk-ln tk-ln-role" d="M{_n(x(self.roles[0].start))} {M}H{_n(x(self.main_end))}"/>']
        for m in self.degrees:
            a, y = x(m.start), deg_y(m.lane)
            b = x(m.end) if m.end is not None else x(self.now)
            r = min(12, (b - a) / 2)
            if m.end is None:
                d = f"M{_n(a)} {M}C{_n(a + r * .6)} {M},{_n(a + r * .25)} {y},{_n(a + r)} {y}H{_n(b)}"
                out.append(_dot(b, y, "tk-tip tk-tip-deg", 3.5))
            else:
                d = (f"M{_n(a)} {M}C{_n(a + r * .6)} {M},{_n(a + r * .25)} {y},{_n(a + r)} {y}H{_n(b - r)}"
                     f"C{_n(b - r * .25)} {y},{_n(b - r * .6)} {M},{_n(b)} {M}")
            out.insert(0, f'<path class="tk-ln tk-ln-deg" d="{d}"/>')
            out.append(_text((a + b) / 2, y - 9, m.label, "tk-tx tk-tx-deg", "middle"))
            out.append(_hit(m, _dot((a + b) / 2, y, "tk-dot tk-dot-deg")))
        for m in self.certs:
            a, y = x(m.start), cert_y(m.lane)
            b = x(m.end) if m.end is not None else x(self.now)
            out.insert(0, f'<path class="tk-ln tk-ln-cert" d="M{_n(a)} {M}C{_n(a + 6)} {M},{_n(a + 4)} {y},{_n(a + 14)} {y}H{_n(b)}"/>')
            out.append(_cross(b, y) if m.lapsed else _dot(b, y, "tk-tip tk-tip-cert", 3.5))
            if a - 5 - len(m.label) * CHAR_W >= 2:
                out.append(_text(a - 5, y + 4, m.label, "tk-tx tk-tx-cert", "end"))
            else:  # no room before the branch: write it above the lane, after the diamond
                out.append(_text(a + 28, y - 4, m.label, "tk-tx tk-tx-cert"))
            out.append(_hit(m, _diamond(a + 19, y)))
        out += self._role_hits(lambda t: (x(t), M))
        for label, s, e in self.segs:
            a, b = x(s), x(e)
            out.append(f'<path class="tk-tick" d="M{_n(a)} {band - 9}V{band + 2}"/>')
            if len(label) * CHAR_W <= b - a + 8:
                out.append(_text((a + b) / 2, band, label, "tk-tx", "middle"))
        step = 1 if (W - 2 * P) / (self.hi - self.lo) >= 44 else 2
        for yr in range(math.ceil(self.lo), math.floor(self.hi) + 1):
            if yr % step == 0:
                out.append(_text(x(yr), band + 20, str(yr), "tk-tx tk-tx-muted", "middle"))
        return _svg("tk-wide", W, band + 28, self.label, out)

    def narrow(self) -> Markup:
        W, top, per_year = 340, 16, 56
        y = lambda t: top + (self.hi - t) * per_year
        M = 48 + 14 * self.n_deg
        deg_x = lambda k: M - 18 - 14 * k
        cert_x = lambda k: M + 18 + 14 * k
        lab_x = (cert_x(self.n_cert - 1) if self.n_cert else M) + 16
        out = [f'<path class="tk-ln tk-ln-role" d="M{M} {_n(y(self.roles[0].start))}V{_n(y(self.main_end))}"/>']
        labels: list[tuple[float, str, str]] = []
        for m in self.degrees:
            xl, a = deg_x(m.lane), y(m.start)
            b = y(m.end) if m.end is not None else y(self.now)
            r = min(12, (a - b) / 2)
            if m.end is None:
                d = f"M{M} {_n(a)}C{M} {_n(a - r * .6)},{xl} {_n(a - r * .25)},{xl} {_n(a - r)}V{_n(b)}"
                out.append(_dot(xl, b, "tk-tip tk-tip-deg", 3.5))
            else:
                d = (f"M{M} {_n(a)}C{M} {_n(a - r * .6)},{xl} {_n(a - r * .25)},{xl} {_n(a - r)}V{_n(b + r)}"
                     f"C{xl} {_n(b + r * .25)},{M} {_n(b + r * .6)},{M} {_n(b)}")
            out.insert(0, f'<path class="tk-ln tk-ln-deg" d="{d}"/>')
            out.append(_hit(m, _dot(xl, (a + b) / 2, "tk-dot tk-dot-deg")))
            labels.append(((a + b) / 2, m.label, "tk-tx tk-tx-deg"))
        for m in self.certs:
            xl, a = cert_x(m.lane), y(m.start)
            b = y(m.end) if m.end is not None else y(self.now)
            out.insert(0, f'<path class="tk-ln tk-ln-cert" d="M{M} {_n(a)}C{M} {_n(a - 6)},{xl} {_n(a - 4)},{xl} {_n(a - 14)}V{_n(b)}"/>')
            out.append(_cross(xl, b) if m.lapsed else _dot(xl, b, "tk-tip tk-tip-cert", 3.5))
            out.append(_hit(m, _diamond(xl, a - 19)))
            labels.append((a - 19, m.label, "tk-tx tk-tx-cert"))
        out += self._role_hits(lambda t: (M, y(t)))
        labels += [((y(s) + y(e)) / 2, label, "tk-tx") for label, s, e in self.segs]
        prev = -math.inf
        for target, text, cls in sorted(labels):
            prev = max(target, prev + 14)  # nudge down so labels never overlap
            out.append(_text(lab_x, prev + 4, text, cls))
        for yr in range(math.ceil(self.lo), math.floor(self.hi) + 1):
            out.append(_text(0, y(yr) + 4, str(yr), "tk-tx tk-tx-muted"))
        height = max(y(self.lo), prev + 10) + top
        return _svg("tk-narrow", W, height, self.label, out)


def career_track(bank: Bank, today: date) -> dict | None:
    """Both drawings of the track, or None when the bank has no security-track role."""
    month = f"{today.year:04d}-{today.month:02d}"
    marks = _marks(bank, month)
    if marks is None:
        return None
    track = _Track(*marks, now=years(month))
    return {"wide": track.wide(), "narrow": track.narrow()}
