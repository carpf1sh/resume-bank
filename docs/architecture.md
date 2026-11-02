# Architecture

## Three repos, one direction of flow

```
resume-bank (public)          my-bank (private)                     my-site (public)
  rmgr + schemas + skills  --> pinned by tag in pyproject/uv.lock
                               data/  sources/  interviews/
                               applications/  jobs/inbox/  site/
                               CLAUDE.md (house rules)
                               publish workflow --(leak-guarded build)--> GitHub Pages
```

- **The tool (this repo)** has no personal data. Its tests use generated fixtures and the fictional `examples/sample-bank/`.
- **The bank** is a private repo and the place you work day to day. It holds every fact and is the only place they're edited. Git gives you history and multi-machine sync. Cloning it and running `uv sync` is the whole setup, because the tool comes in as a pinned git dependency and the skills come in as a Claude Code plugin enabled in the bank's `.claude/settings.json`.
- **The site repo** receives only built, leak-checked output, pushed by a deploy key scoped to that one repo.

Tool upgrades are explicit: tag a release here, then run `uv lock --upgrade-package resume-mgmt` in the bank and commit. A publish never picks up tool changes nobody reviewed.

## The bank

| Path | Holds |
|---|---|
| `data/profile.yaml` | name, private contact, public links, `site_url`, summaries per target domain |
| `data/skills.yaml` | skill vocabulary and aliases (used to match postings and tags) |
| `data/roles/<role-id>.yaml` | one job: employer (optionally `public_employer`), title, dates |
| `data/accomplishments/<role-id>/<id>.yaml` | one accomplishment: STAR story, metrics (`verified`), 1–3 resume bullets, `visibility`, `public_text`, `strength`, `sources` |
| `data/certifications.yaml`, `data/education.yaml`, `data/projects/` | lists |
| `sources/` | original resumes and exports (`rmgr extract` writes text copies) |
| `interviews/` | transcripts. Accomplishments cite them in `sources`. |
| `applications/<date>-<company>-<role>/` | frozen posting, `resume.yaml` (bullets cite accomplishment ids), `status.yaml`, built outputs |
| `jobs/inbox/` | postings waiting to be tailored ([contract](job-posting-contract.md)) |
| `site/` | optional extra pages or overrides for the site templates (`index.html` by role, `capabilities.html` by domain) |

## The loop

1. **`/ingest`** reads past resumes and builds roles and accomplishments, deduping the same win across versions. Numbers come in `verified: false`, and the session ends with a report of conflicts and questions.
2. **`/interview`** works through `rmgr gaps` (missing results, unverified metrics, thin target domains, an overdue check-in) one question at a time. It writes to the bank after each topic and keeps a transcript.
3. **`/tailor`** freezes a posting, maps each requirement to evidence, and reports gaps instead of papering over them. It writes `resume.yaml` with every bullet citing its accomplishment ids, then builds docx/PDF/md/txt and runs `rmgr ats-check` (layout, text round-trip, section order, at most 2 pages, keyword coverage).
4. **`/bank-review`** promotes items to `public` one at a time, with a sanitized `public_text` the owner approves.
5. **`/publish`** builds the site behind the leak guard, previews it, shows `rmgr site-diff` against what's live, and pushes only after approval.

Agents draft. `rmgr validate` and the leak guards decide.

## Privacy model

- `visibility` on every accomplishment, certification, and project: `public`, `resume`, or `private`.
- Contact details exist only in `profile.contact` and reach resumes only.
- `public_employer` anonymizes an employer. The site build then fails if the real name appears anywhere in the output.
- The site build's leak guard (`site.find_leaks`) runs on every output file, including the PDF's text and metadata. On a hit, the output is deleted.
- `rmgr leak-scan <folder>` is the stricter check for this repo. Run from a bank, it fails if the folder contains the owner's name, contact details, any item id or employer, or any longer text from the bank. A bank's `leak-terms.txt` adds terms of its own (code names, client names).

## Development against a real bank

```bash
git clone https://github.com/carpf1sh/resume-bank ../resume-bank
uv pip install -e ../resume-bank          # in the bank checkout; the next `uv sync` restores the pin
claude --plugin-dir ../resume-bank        # try skill edits
uv run rmgr leak-scan ../resume-bank      # before committing tool changes
```
