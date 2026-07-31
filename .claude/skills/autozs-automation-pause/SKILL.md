---
name: autozs-automation-pause
description: Pause or resume the AutoZS listing-job worker cleanly, then manually take over a stalled job (verify product identity, fill remaining fields, submit) instead of endlessly polling. Use when a job has stopped making progress (needs_review, or running with no updated_at movement) and the goal is to finish it by hand rather than wait on automation.
---

# AutoZS automation pause

A real, server-enforced pause switch. **Never fake this by editing `ebay_accounts.account_id`
or any other field just to break the browser-account username match** — that field is read
elsewhere as the real expected Chrome username (dashboards, the triage skill, revision jobs),
and corrupting it to "pause" claiming leaves the system lying about its own state to anything
else that reads it. Use the dedicated endpoint below instead.

## Status / pause / resume

```bash
# check
curl -s http://127.0.0.1:8000/listing-jobs/automation-pause

# pause (blocks NEW job claims only — a job already `running` keeps going in its own tab)
curl -s -X POST http://127.0.0.1:8000/listing-jobs/automation-pause \
  -H "Content-Type: application/json" \
  -d '{"paused": true, "reason": "manual takeover of job <id>"}'

# resume
curl -s -X POST http://127.0.0.1:8000/listing-jobs/automation-pause \
  -H "Content-Type: application/json" \
  -d '{"paused": false}'
```

This is enforced inside `start_next_listing_job` (`apps/api/app/services/listing_jobs.py`), the
same place the single-flight "only one running job" check lives — so it needs no extension
changes and survives an API restart (stored as `AppSetting` rows, not in-memory).

Pausing does **not** stop a job that is already `status=running`; that tab keeps executing
independently. Wait for it to leave `running` (`needs_review`, `completed`, `failed`) before
touching the eBay UI — see the hard rule below.

## When to reach for this

The user does not want a running commentary of "still polling." Once a job's `message`/`status`
shows it has actually stopped trying (`needs_review`, or `running` with `updated_at` frozen past
a couple of alarm cycles), stop watching and go finish it:

1. **Pause first** (command above) so nothing new gets claimed while you're in the eBay UI by hand.
2. **Confirm nothing is `status=running`** before opening any `/lstng`, `/sl/list`, or `/sl/prelist`
   URL — `curl -s "http://127.0.0.1:8000/listing-jobs?status=running"` must come back empty. This
   rule has no exceptions; see `autozs-queue-triage` for why (shared `localStorage` workflow key
   corrupts whichever job is mid-flight).
3. **Verify identity before touching anything**: compare the job's `product_id` / `sku` / title
   (`GET /listing-jobs/{id}`) against what's actually loaded in the draft (`assistant_url`'s
   `draftId`, or the product title on the page). Never assume the draft eBay resumes is the one
   you expect — draft cross-contamination is a known failure mode.
4. **Fill what's missing by hand** using the real UI controls, not typed/synthetic values —
   description and date fields silently revert unless set via the actual editor widgets (see
   `autozs-ebay-editor`).
5. **Submit yourself**, then verify the real result: a real item ID on `/sh/lst/scheduled` or
   `/sh/lst/active`, not just the job's own "submitted" message. PATCH the job to `completed`
   with the verified `listing_id` (or `needs_review` with a clear reason if it genuinely can't go
   through) so the DB matches reality.
6. **Resume automation** (command above, `paused: false`) once you're done, so the queue keeps
   draining unattended — the whole point of AutoZS is that it doesn't need a human watching it
   forever. Don't leave it paused after your manual pass.

[[autozs-queue-triage]] [[autozs-ebay-editor]]
