---
name: autozs-queue-triage
description: Diagnose and repair the AutoZS eBay listing worker queue - stalled or zombie runners, needs_review backlogs, false store mismatches, mis-reconciled listings, and deciding whether a job actually listed. Use when jobs are stuck, the worker health light is red, needs_review is climbing, or a job's status looks wrong.
---

# AutoZS queue triage

The goal is always the same: the queue must drain **unattended**. Fix the loop, don't hand-complete listings.

## First: read state, don't guess

```bash
curl -s "http://127.0.0.1:8000/listing-jobs?limit=250"
```

Status light: `http://127.0.0.1:3000/worker-health.html` (green = working, amber = jobs need review, red = ask for help).

Group `needs_review` by the *reason* in `message` before touching anything — the mix tells you which bug you're facing.

## Rules that prevent making things worse

1. **Never open an eBay tab while a job is `running`.** The extension keeps one workflow in `localStorage` under `autozs_ebay_workflow`, shared by every ebay.com tab. A second tab resumes that workflow and writes one product's data into another product's draft. This is how a planter's MPN ended up on a garden hose listing.
2. **Deploying the extension = restarting Chrome = killing the running job.** Only deploy when nothing is `running`, or requeue the victim immediately. Repeated deploys silently destroy the evidence you are trying to collect.
3. **Verify product identity before reconciling.** Confirm the eBay item's title/price matches the product before marking it listed. A job once claimed another product's live listing and created duplicate `ebay_listings` rows.
4. Don't rewrite stored `listing_schedule_at` values; see `autozs-ebay-editor` for the Eastern convention.

## Failure taxonomy

| message contains | meaning | action |
|---|---|---|
| `Windows worker stopped reporting` | 30-min watchdog fired: runner died or never heartbeat | requeue; if it recurs, the runner isn't starting |
| `never confirmed the scheduled listing` | clicked List, eBay refused; item is still a **draft** | read the `eBay showed:` diagnostic in the same message |
| `signed in as X, expected a.m.anim-59` | store mismatch | usually a **stale stored record**, see below |
| `Rejected eBay draft N: it belongs to product M` | draft cross-contamination | requeue; worker makes a fresh draft |
| `eBay needs review: <fields>` | fill validation | the named field is the real blocker |

## Zombie / duplicate runners

Two jobs `running` at once must never happen. Causes seen:

- The API had **no** concurrency check — `start_next_listing_job` now refuses to claim while another job for the account is `running` (a dead runner is released by the 30-min stale sweep, so it cannot deadlock).
- A **stale tab** left open after its job failed kept heartbeating and PATCHed the job back to `running`. The heartbeat now re-reads the job and stops unless it is still `running`.

To clear zombies: PATCH each `running` job back to `queued`, then let the worker re-claim.

## The stored browser-account trap

```bash
curl -s "http://127.0.0.1:8000/ebay/browser-account"
```

Job start compares against this **stored** record. A bad value (once `"options"`, misread from eBay's "Account options" menu) gates the entire queue and does **not** self-heal, because listing editor pages contain no username text to re-detect from. Fix by posting the verified username:

```bash
curl -s -X POST "http://127.0.0.1:8000/ebay/browser-account" \
  -H "Content-Type: application/json" \
  -d '{"account_key":"a.m.anim-59","detected_username":"a.m.anim-59","url":"https://www.ebay.com/sh/ovw","marketplace":"EBAY_US"}'
```

Expect `matched=true, can_list=true`. The only canonical store key is `a.m.anim-59`; never invent a "main-store" alias.

## Did it actually list?

A job saying "submitted" proves nothing. Check eBay itself:

- Scheduled: `https://www.ebay.com/sh/lst/scheduled`
- Drafts: `https://www.ebay.com/sh/lst/drafts` — a title sitting here means it did **not** list
- Growing draft count = failed attempts accumulating; stale drafts get reused and cause cross-contamination

Only mark a job completed when eBay shows a real item ID.

## Requeueing a backlog

Requeue in batches with a message naming the bug that was fixed, so the history stays readable. Jobs serialize behind the single-flight guard, so a large requeue is safe. Prefer proving one job completes end-to-end before requeueing dozens — otherwise a still-broken step just churns the whole backlog.
