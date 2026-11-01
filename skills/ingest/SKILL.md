---
name: ingest
description: Analyze past resumes, cover letters, and LinkedIn exports in sources/ and build or update the accomplishment bank in data/. Use when new source documents are added or the user asks to (re)ingest resumes.
---

# /ingest: build the bank from source documents

Follow the ground rules in CLAUDE.md throughout. Above all: **extract, don't invent.**

## 1. Extract

```bash
uv run rmgr extract
```

This writes `sources/extracted/**/<file>.txt` for every .docx, .pdf, .csv, .txt, and .md in `sources/`. Read the extracted text, not the binaries. If a file errors, tell the user and continue.

On a re-ingest, only files reported `new` or `updated` need analysis. Still check them against the existing bank.

## 2. Read everything, oldest first

Order the sources by the date in the file name or content. For each one, note:
- the roles listed (employer, title, location, dates)
- every bullet and summary claim
- skills, certifications, education, and projects
- for tailored resumes (named after a company) and cover letters, the target company. Their wording is often the strongest version of a claim, and cover letters often hold the story behind a bullet.

## 3. Build the role timeline

Merge each role across all sources into `data/roles/<role-id>.yaml`:
- When sources disagree on a title or dates, prefer the most recent general resume. Record the conflict in the report.
- Promotions within one employer become separate roles if the titles differ.
- `sources`: every file the role appears in.

## 4. Extract accomplishments

For each distinct achievement, write one file: `data/accomplishments/<role-id>/<id>.yaml`.

- **Dedupe across versions.** The same win phrased differently in five resumes becomes ONE accomplishment. Its `resume_bullets` keeps up to 3 of the best distinct phrasings, verbatim from the sources, and its `sources` lists every file it came from.
- Fill `star` only with what the sources actually say. Leave fields you can't support as `null`.
- `metrics`: only numbers that appear in a source, with `verified: false`.
- `skills`: use canonical names from `data/skills.yaml` where they match. If a genuinely relevant skill is missing from the taxonomy, add it there.
- `domains`, `frameworks`: tag only what the text supports.
- `visibility: resume` by default. Never `public` during ingest; The owner promotes items later (`/bank-review`).
- `strength`: your 1–5 estimate of impact, based on scope and results stated in the sources.
- Duties without an outcome ("Responsible for...") still get captured when they show scope, but give them `strength: 1` or `2` and list them in the report as candidates for the interview.
- Leave `last_reviewed` empty. The owner hasn't confirmed anything yet.

## 5. Other files

- `data/profile.yaml`: name, contact (from the most recent resume), headline, target roles, one summary per target domain. Use the most recent summaries verbatim where possible.
- `data/certifications.yaml`, `data/education.yaml`, `data/projects/*.yaml`.

## 6. Validate

```bash
uv run rmgr validate --strict
```

Fix every error and warning.

## 7. Write the ingest report

Write `interviews/YYYY-MM-DD-ingest.md` with:
- **Sources analyzed**: the list, with dates.
- **Timeline**: role, dates, and accomplishment count.
- **Conflicts**: title/date/metric disagreements between sources, and which one you picked.
- **Weak items**: accomplishments missing a result or metric, and duty-style bullets.
- **Coverage gaps**: roles with few items, target domains (cloud / AI / architecture) with little evidence, and periods with nothing.
- **Questions for the first interview**: specific questions, grouped by role. `/interview` reads these.

## 8. Hand off

Summarize the counts and the top conflicts for the owner, and ask them to review `git diff`. Commit only when they ask, with a message like `bank: ingest <n> sources (+<m> accomplishments)`.
