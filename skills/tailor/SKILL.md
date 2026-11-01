---
name: tailor
description: Tailor the owner's resume to a job posting - analyze the posting, map requirements to bank evidence, report gaps, write applications/<date>-<company>-<role>/resume.yaml, and build ATS-checked docx/PDF/Markdown. Use when the user gives a job posting (URL, file, or jobs/inbox/*.md) or runs /tailor.
---

# /tailor: one posting → one ATS-safe, fully cited resume

Argument: a posting URL, a file (`.md`, `.docx`, `.pdf`, `.txt`), or `jobs/inbox/<file>`.

Follow CLAUDE.md throughout. **Rephrase, never invent.** Every bullet must come from a bank accomplishment and cite its id. A requirement without evidence is a gap you report, never something you write around.

## 1. Freeze the posting

1. If the argument is a URL, fetch the page and save the description as `jobs/inbox/<company>-<role>.md`, following the job posting contract (`docs/job-posting-contract.md` in the resume-bank tool repo) (frontmatter `company`, `title`, `url`, `location`, `remote`, `source`, `found_at`). Copy the description; don't summarize it.
   Then run `uv run rmgr inbox`. If the posting shows as `duplicate`, stop and tell the owner which application it matches.
2. Run `uv run rmgr new application <file> [--company X --title Y --url U] --role-slug <short-role>`. It creates `applications/YYYY-MM-DD-<company>-<role>/` with `posting.md` (frozen copy) and `status.yaml` (stage `drafted`). Keep `--role-slug` to 2–3 words, e.g. `cloud-security-architect`. If the source was in `jobs/inbox/`, delete that file afterwards, since `posting.md` is now the frozen copy.
3. Never edit the body of `posting.md` after this. You may add frontmatter `keywords` (step 2).

## 2. Analyze → `analysis.md`

Read the posting and write `applications/<dir>/analysis.md`:
- **Read of the posting:** level (IC / lead / manager), must-haves, responsibilities, nice-to-haves, keywords, seniority signals.
- **Requirement → evidence table:** each requirement, the accomplishment ids that back it, and a fit rating (Strong / Medium / Weak / Gap). Find evidence by reading `data/accomplishments/**`. Use `skills`, `domains`, `star`, and `resume_bullets`, and match terms through `data/skills.yaml` aliases.
- **Gaps:** every requirement with no evidence or only weak evidence, plus years-of-experience mismatches. Be blunt.
- **Questions for a targeted interview:** short, specific questions that could close each gap.
- **Bank issues found:** conflicting numbers, bad aliases, unverified metrics you relied on.

Add posting terms that `data/skills.yaml` doesn't already match (tool names, languages, phrases like "alert fidelity") to `keywords:` in the `posting.md` frontmatter, so `rmgr ats-check` measures them.

## 3. Offer a targeted interview (optional)

If there are gaps, show the owner the gap list and the questions. Ask whether to (a) run a short targeted interview now, which follows steps 2–3 of the interview skill and writes to the bank with a transcript at `interviews/YYYY-MM-DD-tailor-<company>.md`, or (b) tailor with the bank as it is. Only answers they give can close a gap.

## 4. Write `resume.yaml`

Schema: `TailoredResume` in `resume_mgmt/models.py` (`schemas/tailored-resume.schema.json` in the tool repo).

- `posting: posting.md`.
- `summary`: start from the matching domain summary in `data/profile.yaml` (`general` if there's none for this domain). Mirror the posting's terms, but every claim must trace to a cited accomplishment or the profile. No years-of-experience claims the roles don't support.
- `roles`: security roles, newest first (the renderer sorts by date anyway). Skip `track: other` roles. Set `condensed: true` for old or irrelevant roles (title and dates only).
- `bullets`:
  - Pick the strongest relevant items (`strength`, posting fit). Aim for 5–9 bullets for the current role, 3–5 for the previous one, and 1–3 for older ones.
  - Rephrase to mirror the posting's terminology: strong verb first, the metric in the bullet, **25 words or fewer** (the validator warns past that).
  - `sources:` lists every accomplishment id the bullet draws from. All of them must belong to that role and must not be `private`. The validator enforces this.
  - Don't upgrade verbs ("facilitated" doesn't become "led"), scope, or numbers. Don't reuse the same metric in two bullets.
  - Note in a YAML comment if a metric is `verified: false`. The owner should confirm it before sending.
- `skills`: only canonical names or aliases that exist in `data/skills.yaml` and that cited accomplishments demonstrate. Leave out tools that were only evaluated.
- `certifications`: ids from `data/certifications.yaml` (not `private`). `projects`: ids if relevant. `include_education: true` unless the owner says otherwise.

Run `uv run rmgr validate --strict` and fix everything.

## 5. Build and check

```bash
uv run rmgr build resume applications/<dir>      # docx + pdf (LibreOffice) + md + txt
uv run rmgr ats-check applications/<dir>         # layout, text round-trip, section order, pages, keywords
```

Iterate until every check passes:
- **Over 2 pages:** condense older roles, drop the weakest bullets, tighten the summary. Never shrink the font or margins.
- **Lost text / section order:** a renderer bug. Fix the code, don't work around it in content.
- **Low keyword coverage:** for each missing keyword, either an existing cited accomplishment honestly supports the posting's word (rephrase the bullet), or it's a gap (leave it and list it in `analysis.md`). Never add a keyword without evidence.

Append the final ATS result (checks, pages, coverage, missing keywords and why) to `analysis.md`.

## 6. Hand off

1. `status.yaml` stays `stage: drafted`. When the owner applies, run `uv run rmgr stage applications/<dir> applied --note "<where/how>"`, and use the same command for later stages. It updates `stage` and appends a dated `history` entry.
2. Show the owner: the fit summary, the gap list, the tailored bullets with their cited ids, the unverified metrics used, and the paths to the docx/PDF.
3. Offer to commit: `apply: <company> <role>` (include any bank changes from a targeted interview in the same commit only if they agree). Commit only when they say yes.
