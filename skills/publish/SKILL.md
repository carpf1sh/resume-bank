---
name: publish
description: Publish the bank owner's public portfolio - build the site with the leak guard, preview it locally, show which items become public, then push after the owner approves. Use when the user runs /publish or asks to update or deploy the public site.
---

# /publish: preview, confirm, push

The site is built from `data/` (plus any pages in the bank's `site/` folder) by `uv run rmgr build site`, using `profile.site_url` as its address. A workflow in the bank repo deploys it; the tool repo's `examples/workflows/publish-site.yml` is the reference version, which pushes `build/site/` to a separate public repo served by GitHub Pages. The workspace CLAUDE.md names the actual public repo, workflow, and trigger paths.

**Nothing goes live without the owner's explicit OK in this session.** Merging to the bank repo's `main`, or running the publish workflow, publishes.

## 1. Build and check

```bash
uv run rmgr validate --strict
uv run rmgr build site
```

`build site` also renders the general PDF resume (`<Name>-Resume.pdf`, linked from the hero) from the same public set: public location and links instead of contact details, and `public_text` instead of resume bullets. It needs LibreOffice. `--no-pdf` skips the PDF for a quick local preview, but never publish that way.

`build site` fails, and deletes the output, if any of these appear in it: a non-public id, a resume bullet, STAR text, a role summary, a contact detail, or an anonymized employer name. Never work around a leak-guard failure. Fix the data (or the template that leaked it) and rebuild.

## 2. Preview locally

Serve `build/site/` and open it:
- In the desktop app: `preview_start` with a `site` configuration in `.claude/launch.json` that serves `build/site/` at http://localhost:8000/.
- Otherwise: `uv run python -m http.server 8000 -d build/site`, then open http://localhost:8000/.

Check each of these, and tell the owner what you saw:
- The hero shows the name, headline, public summary, links, and the "Resume (PDF)" link. It has no email, phone, or private location.
- The PDF reads well and has no email, phone, or private location. (The leak guard scans its text too.)
- Each public highlight on the timeline sits under the right role. The domain and skill chips filter it, and clicking an active chip clears it.
- The career track above the experience list shows each security role, every public degree and certification that overlaps the security career, and lapsed certs ending in an x. Hovering or tapping a mark shows its detail line, and at phone width the track turns vertical. If a short label reads badly, set `short_name` on the cert.
- The skills matrix, certifications, projects, education, and any overlay pages from `site/` look right.
- Light mode, dark mode, and a phone-width viewport (375px) all work.

## 3. Show what changes

```bash
uv run rmgr site-diff            # vs origin/main, i.e. what's live now
```

List each `added` / `changed` / `removed` item with its public text. Point out anything newly public since the last publish. If nothing changed, say so and stop.

## 4. Push (only after the owner approves)

Ask the owner to confirm the preview and the list. Then:
- **Bank or overlay changes not on `main` yet:** commit (`site: ...` or `bank: ...`), push the branch, and open a PR. Merging it to `main` triggers the publish. Tell the owner that merging publishes.
- **Already on `main`** (e.g. a re-publish): `gh workflow run publish-site.yml --ref main`.

When the run finishes (`gh run list --workflow publish-site.yml --limit 1`), confirm the live site at `profile.site_url` shows the new content (Pages can take a minute or two). Report the run URL and the public repo commit.

## If something goes wrong

- **The workflow fails at "Build site":** the leak guard or validation caught something. Read the log and fix the data.
- **The workflow fails at "Push":** check that the deploy key on the public repo still has write access and that its secret is set in the bank repo.
- **Something has to come down:** set the item back to `visibility: resume`, then publish again. The public repo's history still has the old page. If something sensitive went out, tell the owner right away, because removing it from history needs their action on the public repo.
