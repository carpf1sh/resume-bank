# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's [private vulnerability reporting](https://github.com/carpf1sh/resume-bank/security/advisories/new) (Security tab → "Report a vulnerability"). Don't open a public issue.

Include what you found, how to reproduce it, and the version or commit. You'll get an acknowledgement within 7 days.

## Scope

In scope: the `rmgr` CLI and its renderers, the leak guard (`rmgr build site`, `rmgr leak-scan`), the site templates, the Claude Code skills, and the example workflows. Of particular interest is anything that lets `visibility: resume` or `private` data, or `profile.contact`, reach the public site.

Out of scope: the fictional sample bank's content, and third-party dependencies (report those upstream; Dependabot tracks them here).

## Supported versions

Only the latest release tag gets fixes.
