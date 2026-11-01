---
name: bank-review
description: Review the accomplishment bank with its owner - choose what goes public (sanitized public_text, visibility public), refresh the public profile, and do the quarterly cleanup (duplicates, stale metrics). Modes - publish (default), cleanup. Use when the user runs /bank-review, wants to decide what appears on the public site, or asks to promote items to public.
---

# /bank-review: decide what the public site shows

Argument: `publish` (default) or `cleanup`.

Follow CLAUDE.md throughout. **The owner approves every public item, one at a time.** Nothing becomes `visibility: public` on your judgment alone, and nothing is committed until they have reviewed the diff.

## publish

### 1. Find candidates

Load the bank (`uv run rmgr validate` must pass) and list accomplishments that are not yet public, strongest first:

```bash
uv run python -c "from pathlib import Path; from resume_mgmt.load import load_bank; b=load_bank(Path('.')); [print(a.strength, a.id, '|', ', '.join(a.domains), '|', a.title) for a in sorted(b.accomplishments.values(), key=lambda a: (-(a.strength or 0), a.id)) if a.visibility != 'public']"
```

Rank by:
1. `strength` (5 first).
2. Fit with the target domains in `profile.target_domains` then other security domains.
3. Recency.

Skip:
- `track: other` roles (pre-security work): the site's timeline doesn't show them.
- `visibility: private` items: never propose these. Mention them only if the owner asks.
- Items whose whole story is a confidential incident, vulnerability, or client detail that can't be told without the detail. Say why you skipped them.

Aim for a first set of roughly 8–15 public items that covers each security role on the timeline with at least one or two, weighted to the last three years.

### 2. Draft a `public_text` for each candidate

One line, about 12–25 words, past tense for ended roles and present tense for the current one. Build it from `title`, `star`, and `resume_bullets`, and apply these rules:

- **No maturity-revealing baselines.** Keep "before" numbers that show a weakness in a current employer's program (MTTR in days, containment over a day, N untriaged findings, "from 19 tenants to 2") out of public text. Percentages and outcomes are fine ("cut mean time to respond by 60%"). Apply any stricter sensitivity rules in the workspace CLAUDE.md.
- **No specific controls.** Describe the principle ("hardened identity and SaaS platforms against account takeover"), never the setting, rule, product configuration, or detection logic.
- **No internal names.** No internal system names, project code names, client names, vulnerability ids, or incident details. Well-known vendor products (Wiz, Okta, AWS) are fine when they describe the platform, not a weakness in it.
- **Only verified metrics.** If a metric has `verified: false`, leave the number out or ask the owner to confirm it first (then set `verified: true`).
- **Never add claims.** Rephrase and generalize; never upgrade verbs, scope, or numbers.
- **Don't copy a resume bullet verbatim.** The leak guard treats `resume_bullets` text on the page as a leak; write the public line fresh.
- **Check the skill tags too.** The site tags each item with its `skills`. If one names an internal platform, a specific control, or a vendor the owner doesn't want tied to the employer, propose `public_skills:` (a subset of `skills`) for that item.
- **Anonymize when needed.** If the employer can't be named publicly, propose a `public_employer` for the role (e.g. "Global governance SaaS company"). The build's leak guard then fails if the real employer name appears anywhere on the page.

### 3. Walk the owner through them, one at a time

For each candidate, strongest first, show:

```
[3/12] acme-2024-cnapp-rollout  (strength 5, cloud-security)
Bank:     <the strongest resume bullet>
Proposed: <public_text>
Dropped:  <what you left out and why: baseline, control detail, unverified metric>
```

Ask: approve, edit (they give wording), or skip (stays `resume`). Use AskUserQuestion for a batch of up to 4 items when they want it faster, but show the full proposed text in each option's description.

On approve or edit, update `data/accomplishments/<role-id>/<id>.yaml`:
- `public_text:` the approved wording, exactly (and `public_skills:` if agreed).
- `visibility: public`.
- `last_reviewed:` today.

The owner can stop at any point; keep what's approved so far.

### 4. Public profile

Show the current `headline`, `location`, `links`, and `public_summary` in `data/profile.yaml`, and propose updates:
- `headline` matches the current role's functional title (from `data/roles/`), not an old one.
- `public_summary`: 2–3 sentences, built only from items that are now public and from the profile's domain summaries. Same sensitivity rules. No contact details, no claims without public evidence, no years-of-experience numbers the roles don't support.
- `location` is shown publicly. Ask whether they want the city or something broader ("Denver metro", "Remote, US"). `contact.location` stays on resumes only.

Also confirm each certification, degree (including `honors`), and project is fine to show. They default to `visibility: public`. Set `visibility: resume` on any they want hidden.

### 5. Check and hand over

```bash
uv run rmgr validate --strict
uv run rmgr build site          # fails if anything private leaks
uv run rmgr site-diff           # what changes on the live site vs origin/main
```

Show the owner the `site-diff` output and the YAML diff (`git diff -- data/`). Commit only after they approve, as `bank: review YYYY-MM-DD (+N public)`. Then offer `/publish`.

## cleanup

Quarterly hygiene. Report first, change only what the owner approves:
- **Duplicates:** accomplishments that tell the same story (same role, overlapping skills and STAR). Propose a merge that keeps the stronger metrics and all `sources`.
- **Unverified metrics:** list every `metrics[].verified: false`; ask the owner to confirm or correct each.
- **Stale reviews:** items with no `last_reviewed`, or older than a year, with strength ≥ 3.
- **Public text drift:** public items whose STAR or metrics changed after `public_text` was written.
- `uv run rmgr gaps` for anything else.
