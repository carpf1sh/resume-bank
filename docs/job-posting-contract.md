# Job-posting contract (`jobs/inbox/`)

This is the seam between a job finder and this repo. A job finder can be a separate repo, a script, or a scheduled Claude routine. Its only job here is to write files in this shape into `jobs/inbox/`. `/tailor` picks them up from there.

## File

- One posting per file: `jobs/inbox/<company>-<role>.md`, lowercase kebab-case (e.g. `acme-cloud-security-architect.md`).
- UTF-8 Markdown: YAML frontmatter between `---` lines, then the posting description.
- The body is the **raw description**, copied rather than summarized. Keep its headings and bullet lists. Once the posting is frozen into an application, nothing edits the body.

```markdown
---
id: acme-cloud-security-architect-4821
company: Acme
title: Cloud Security Architect
url: https://boards.example.com/acme/jobs/4821
location: Denver, CO
remote: true
source: greenhouse
found_at: 2026-11-02
salary: $180k–$210k
match_hints: [cloud-security, ai-security]
---

# Cloud Security Architect

## What you'll do
- ...
```

## Frontmatter

The schema is `PostingMeta` in `src/resume_mgmt/models.py`, exported as `schemas/posting.schema.json`. Unknown keys are rejected.

| Key | Required | Meaning |
|---|---|---|
| `company` | yes | Employer name as the posting shows it |
| `title` | yes | Job title as the posting shows it |
| `id` | no | Stable slug from the finder (e.g. board name + job id), for its own bookkeeping |
| `url` | no, but strongly preferred | Canonical posting URL. It is the main duplicate key |
| `location` | no | Free text |
| `remote` | no | `true` / `false` |
| `source` | no | Where it came from: a job board name, a URL, a file |
| `found_at` | no | `YYYY-MM-DD` the finder saw it |
| `salary` | no | Free text, as posted |
| `match_hints` | no | Why the finder picked it, e.g. domain names (`cloud-security`) or matched terms |
| `keywords` | no | Posting terms for `rmgr ats-check` to measure that `data/skills.yaml` doesn't already match. Usually `/tailor` adds these |

## Avoiding duplicates

Before writing a posting, a finder should read the application log:

```bash
uv run rmgr applications --json   # [{folder, company, title, url, stage, created, updated}, ...]
```

Skip a posting if its URL matches one in the log (compared without scheme, `www.`, query string, fragment, or trailing slash), or if its company + title match. `uv run rmgr inbox` applies the same rules to what is already in the inbox. It reports each file as `new`, `duplicate` (with the application or inbox file it matches), or `invalid`. `rmgr validate` warns about invalid inbox files.

## Lifecycle

1. The finder writes `jobs/inbox/<company>-<role>.md`.
2. The owner runs `/tailor jobs/inbox/<file>`. That calls `rmgr new application`, which freezes the posting into `applications/YYYY-MM-DD-<company>-<role>/posting.md` (with `source: jobs/inbox/<file>`) and creates `status.yaml` at stage `drafted`.
3. Delete the inbox file once its application exists. `posting.md` is the frozen copy, and `rmgr inbox` flags any leftover file as a duplicate.
4. Stage changes go through `rmgr stage applications/<dir> applied --note "..."` (then `screening`, `interviewing`, `offer`, `rejected`, `withdrawn`, `closed`). Each change adds a dated history entry.
