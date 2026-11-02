# resume-bank

An evidence-backed career bank, and the tooling that turns it into tailored, ATS-safe resumes and a public portfolio site, with Claude Code skills that do the interviewing and drafting.

The idea: keep every career claim once, as structured data with its full story and its source, then generate every resume and the public site from that data. AI agents interview you, draft, and tailor. Deterministic code checks their work. You approve anything that leaves the repo.

**Live demo:** https://carpf1sh.github.io/resume-bank/ is the portfolio built from the fictional sample bank (Jane Doe), with its PDF resume. It redeploys on every change to the sample bank or the tool.

This repo is the tool. Your bank lives in a **separate private repo** that pins this one. See [docs/architecture.md](docs/architecture.md).

## What's in it

| Piece | Where |
|---|---|
| `rmgr` CLI: validate, gap report, extract, tailor/build resumes, ATS check, build site, leak scan | `src/resume_mgmt/` |
| JSON schemas for every bank file (generated from the pydantic models) | `schemas/` |
| Claude Code plugin: `/ingest`, `/interview`, `/tailor`, `/bank-review`, `/publish` | `skills/`, `.claude-plugin/` |
| Site templates (Jinja) | `src/resume_mgmt/templates/site/` |
| A fictional sample bank to try everything on (deployed as the live demo by `.github/workflows/sample-site.yml`) | `examples/sample-bank/` |
| A reference publish workflow (bank repo → public Pages repo) | `examples/workflows/publish-site.yml` |
| Posting format for an external job finder | `docs/job-posting-contract.md` |

## Try it

```bash
uv sync
uv run rmgr validate --strict --root examples/sample-bank
uv run rmgr gaps --root examples/sample-bank
uv run rmgr build site --root examples/sample-bank --no-pdf     # -> examples/sample-bank/build/site/ (index.html by role, capabilities.html by domain)
uv run pytest
```

PDF output (tailored resumes and the site's resume) needs LibreOffice. Set `RMGR_SOFFICE` if `soffice` isn't on PATH.

## Use it for your own bank

1. Create a **private** repo with the layout in `examples/sample-bank/`.
2. Add the tool as a pinned dependency in its `pyproject.toml`:

   ```toml
   [project]
   name = "my-bank"
   version = "0"
   requires-python = ">=3.12"
   dependencies = ["resume-mgmt"]

   [tool.uv]
   package = false

   [tool.uv.sources]
   resume-mgmt = { git = "https://github.com/carpf1sh/resume-bank", tag = "v0.1.0" }
   ```

3. Enable the skills in its `.claude/settings.json`:

   ```json
   {
     "extraKnownMarketplaces": {
       "resume-bank": { "source": { "source": "github", "repo": "carpf1sh/resume-bank" } }
     },
     "enabledPlugins": { "resume-bank@resume-bank": true }
   }
   ```

4. Write a `CLAUDE.md` with your own house rules. The skills defer to it for things like what may never appear publicly.
5. Put old resumes in `sources/`, then run `/ingest`, `/interview`, `/tailor`, `/bank-review`, `/publish`.

## Guarantees the code enforces

- **Every claim traces to evidence.** Validation fails on unknown ids, missing `sources` files, and tailored bullets that cite private or other-role accomplishments.
- **Visibility is per item.** `public` items reach the site only through their `public_text`. `resume` items reach tailored resumes only. `private` items never leave the bank.
- **The site build fails on a leak.** It scans every output file, including the PDF's text, for non-public ids, resume bullets, STAR text, contact details, and anonymized employer names.
- **`rmgr leak-scan <folder>`**, run from a bank, checks that a folder (like a checkout of this repo) contains nothing from that bank at all.

## License

Apache-2.0. See [LICENSE](LICENSE). The bundled Geist fonts are under the SIL Open Font License (see `src/resume_mgmt/templates/site/fonts/LICENSE.txt`).
