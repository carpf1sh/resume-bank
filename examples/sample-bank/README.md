# Sample bank

A small, entirely fictional bank (Jane Doe and made-up employers). It shows the layout and lets you try the tool:

```bash
uv run rmgr validate --strict --root examples/sample-bank
uv run rmgr gaps --root examples/sample-bank
uv run rmgr build resume examples/sample-bank/applications/2026-01-15-fabrikam-cloud-security-architect --root examples/sample-bank --no-pdf
uv run rmgr build site --root examples/sample-bank --no-pdf
```

Your own bank lives in a separate private repo with the same layout. See `docs/architecture.md`.
