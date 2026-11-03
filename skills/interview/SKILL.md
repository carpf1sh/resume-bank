---
name: interview
description: Interview the bank's owner to add or strengthen accomplishments in the bank. Modes - gaps (work the gap report), checkin [period] (capture recent wins), role:<role-id> (deep dive on one job). Use when the user asks to be interviewed, wants to add accomplishments, or runs /interview.
---

# /interview: grow the accomplishment bank

Arguments: `gaps` (default), `checkin [since YYYY-MM]`, or `role:<role-id>`.

Follow CLAUDE.md throughout. **The owner's answers are the only new evidence.** Never fill a field with something they didn't say.

## 1. Prepare (silently, before the first question)

1. Run `uv run rmgr gaps --json --limit 40`.
2. Read the most recent files in `interviews/`, including the ingest report. Collect the `## Next questions` sections that haven't been answered yet; they carry over between sessions.
3. In `role:` mode, read every accomplishment for that role. In `checkin` mode, find the last check-in date (the newest `interviews/*-checkin.md`) and the current role.
4. **Create the transcript now** at `interviews/YYYY-MM-DD-<mode>.md` (add `-2` if the name exists), using the template below. Accomplishments you write will cite it in `sources`, and validation requires the file to exist.
5. Pick 3–5 topics for the session, in this order: carried-over questions, then the highest-priority gaps for this mode. Briefly tell the owner the agenda, about how long it will take, and that they can say "stop" or "skip" any time.

## 2. Ask

- **One question at a time.** Wait for the answer. Keep each question short and specific, and name the accomplishment or period it's about.
- Use plain chat for open questions. Use AskUserQuestion only for quick choices: resolving a conflict between two values, picking `visibility`, or confirming a role assignment.
- **Dig for the STAR story, then quantify.** Follow-ups by topic:
  - *Scale:* how many accounts / subscriptions / workloads / users / engineers / teams / log sources / TB / dollars?
  - *Before vs. after:* baseline, outcome, and time frame. How was it measured? Is it an estimate?
  - *Your role:* what did you personally design, decide, build, or lead, versus what the team did? How big was the team?
  - *Architecture:* what alternatives did you weigh? Why that design? What threat model, frameworks (NIST, CIS, CSA, MITRE ATT&CK / ATLAS, OWASP LLM Top 10), and controls were involved?
  - *AI security:* securing AI tools and agents (MCP servers, Claude Code, Cursor), AI usage policy, data leakage controls, prompt injection, AI vendor/feature risk reviews, model and data supply chain, AI governance.
  - *Cloud:* account/org structure, guardrails (SCPs, policies), IaC, identity, posture management, cloud-native detection.
- If an answer is vague, ask one follow-up. If it's still vague, record what you have, add a note to `## Next questions`, and move on. Don't badger.
- **Confidentiality:** when an answer names a client, an incident, an internal system, or a vulnerability, ask whether it can be public. Offer a sanitized one-line `public_text`.
- For an estimate, store it with `verified: false` and say so in the metric description ("approx."). The owner saying "yes, that's right" makes it `verified: true`.

## 3. Record after each topic (not at the end)

- **New accomplishment:** write `data/accomplishments/<role-id>/<id>.yaml`, following CLAUDE.md conventions. `sources` includes the transcript path.
- **Existing accomplishment:** edit in place. Add the transcript to `sources`, fill in the STAR/metrics, add or refresh up to 3 `resume_bullets`, and set `last_reviewed: <today>` for anything the owner confirmed.
- **Resolved conflict:** update the value everywhere it appears (roles, certifications, metrics) and note the decision in the transcript.
- **New skill or framework:** add it to `data/skills.yaml`, in a category whose `layer` fits (or give the skill its own `layer`) so it lands in the right place on the site's skills map.
- Run `uv run rmgr validate --strict` and fix any problems before the next question.
- Show the owner the new or changed bullets (not the full YAML) and ask "Anything to correct?" before moving on.

Writing bullets: strong verb first, the metric in the bullet, 25 words or fewer, their terminology and no buzzwords. Rephrasing their words is fine. Adding claims is not.

## 4. Close

When the agenda is done, the owner stops, or about 30–40 minutes have passed:
1. Finish the transcript: the summary, the created/updated lists, and `## Next questions` (unanswered questions, follow-ups, numbers they'll look up).
2. Run `uv run rmgr validate --strict` and `uv run rmgr gaps --limit 10`. Tell them how the top gaps moved.
3. Offer to commit, with a message like `bank: interview YYYY-MM-DD (<mode>) +N new, M updated`. Commit only when they say yes.

## Transcript template

```markdown
# Interview: YYYY-MM-DD (<mode>)

**Agenda:** <topics>

## Summary
<3–5 lines: what was learned>

## Created
- `<id>`: <title>

## Updated
- `<id>`: <what changed>

## Decisions
- <conflict resolved, visibility chosen, role reassigned>

## Notes
### <topic>
- Q: <question, short>
- A: <the owner's answer, condensed but faithful; keep numbers and names exactly>

## Next questions
- [ ] <question for the next session>
```

## Modes at a glance

| Mode | Focus | Typical agenda |
|---|---|---|
| `gaps` | `rmgr gaps` priorities + carried-over questions | domain coverage (weakest target domain first), then strongest items missing results, then conflicts |
| `checkin [since]` | what's new since the last check-in (default: since the last check-in, or 3 months) | projects shipped, incidents handled, designs, tools adopted, metrics moved, people mentored, certs, talks, OSS; then any role or title change |
| `role:<id>` | everything in one job | scope and team, then each existing item's STAR and metrics, then "what else did you do there that's not on any resume?" |
