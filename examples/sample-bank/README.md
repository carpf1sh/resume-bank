# Sample bank

An entirely fictional bank (Jane Doe and made-up employers). It shows the layout, lets you try the tool, and is deployed as the live demo at https://carpf1sh.github.io/resume-bank/ (eight security roles, 14 public highlights, plus resume-only and private items the leak guard keeps off the site). `site/` adds a how-it-works page over the packaged templates, the way a real bank can.

Try it:

```bash
uv run rmgr validate --strict --root examples/sample-bank
uv run rmgr gaps --root examples/sample-bank
uv run rmgr build resume examples/sample-bank/applications/2026-01-15-fabrikam-cloud-security-architect --root examples/sample-bank --no-pdf
uv run rmgr build site --root examples/sample-bank --no-pdf
```

Your own bank lives in a separate private repo with the same layout. See `docs/architecture.md`.
