# Paste this into the other account

---

Continue the AutoZS eBay listing work. Read `C:\AutoZS\repo\docs\AUTOZS-HANDOFF-2026-07-31.md`
first — it has the full runbook, the DOM landmarks, and the known failure modes. This message
is the delta on top of it.

## Where things stand

- Outstanding listing jobs: **59**. Target: **50** — so **9 more listings**.
- Count them with:
  ```bash
  python -c "import sqlite3;c=sqlite3.connect(r'C:\AutoZS\data\autozs.db');print(c.execute(\"SELECT count(*) FROM listing_jobs WHERE status IN ('needs_review','queued','ready_to_save')\").fetchone()[0])"
  ```
- **Automation is PAUSED** and must stay paused while you work by hand, or a background job
  will hijack the tab you are editing. Resume only when you are done:
  ```bash
  curl -s -X POST http://127.0.0.1:8000/listing-jobs/automation-pause \
    -H "Content-Type: application/json" -d '{"paused": false}'
  ```
- After 50, the user is moving on to **Depop** (not "depot" — that was a typo in the chat).
- 27 listings were completed by hand across the two sessions, all verified with real eBay
  item IDs. Aug 1–4 are fully covered; Aug 5 is filled through 9:00 PM ET; Aug 6 has two.

Next candidates, earliest first: jobs **98, 99, 100, 101, 103, 104, 106, 107, 108**
(Aug 6 7:20 PM ET onward). Job 103 is the Rhino watering can, which has failed repeatedly on
item specifics — skip it and take job 104 if it fights you.

## The per-listing loop (~4–6 tool calls once you have the rhythm)

1. `curl -s "http://127.0.0.1:8000/listing-jobs/<ID>"` → grab `assistant_url` and
   `listing_schedule_at`.
2. Navigate to the `assistant_url` in the Chrome tab. The extension builds the draft:
   category, price, photos, date and time all land correctly. It will fail on the
   description — that is expected, ignore the error.
3. Read the draft state (photos, Brand, Type, day, time, descLen, price) in one JS call.
4. Fix whatever is wrong — usually **Type**, sometimes **Brand**, sometimes **photos are 0**.
5. **Write the description LAST**, immediately before submitting.
6. Submit, capture the `ID-<item>` from the confirmation.
7. Record it (see "Recording" below).

## Corrections to the handoff — read these, they cost real time to learn

**1. The description method in the handoff was backwards.** `execCommand('insertHTML')` into
the iframe's `[contenteditable]` returns `true` and reads back the full length, then eBay's
validation re-render **wipes it to zero** and the submit is rejected. What actually persists
is the **HTML-source textarea via the native value setter**, because that is a real
React-controlled input:

```js
// enable "Show HTML Code" first if it is off, then:
var ta = document.querySelector('textarea[id*="rawEditor"], textarea[name="description"]');
var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
setter.call(ta, htmlString);
ta.dispatchEvent(new Event('input',  { bubbles: true }));
ta.dispatchEvent(new Event('change', { bubbles: true }));
```

Verify by re-reading after ~1.5s, not immediately — an immediate read gives a false pass.
Expect eBay to normalise ~10 chars of whitespace (3272 → 3262); that is fine, not a failure.

**2. Description must be written LAST.** Anything that triggers a re-render — especially the
calendar picker — silently drops it. On job 97 the date fix wiped a description that had
already verified clean. Order: photos → Brand → Type → date/time → **description** → submit.

**3. Re-running the assistant fill is destructive.** Most drafts arrive with **0 photos**, and
the extension's own status message only mentions the description — so a photo-less listing
looks "ready". Clicking **Fill Listing** in the assistant panel uploads them correctly, but
the same pass also **resets Brand to "Unbranded" and the schedule date to today**. Always
re-check and restore both afterwards. It can also duplicate photos (5 uploaded on a 4-image
product); dedupe via Photos → Select → tick extras → Delete.

**4. `autozs_autosubmit=1` can publish mid-edit.** On job 94 it fired before I finished and
published with Brand "Unbranded". I had to revise the live listing. If you see the assistant
still running, wait for it to settle before touching fields.

**5. When a dropdown refuses to change an already-set value,** use eBay's **"Suggested item
specifics"** panel — the one-click checkboxes work where scripted and real clicks both failed
(job 86, three attempts). Caveat: suggestions **add** a value rather than replace it, so on
job 95 Type became "Amphora (+1)" and I had to deselect Amphora under "Selected".

**6. Type defaults are frequently wrong.** The extension picks the first alphabetical option:
`Coil Hose` for hoses, `Cleaning Gun Nozzle` for nozzles, `Amphora` for planters. Correct to
`Standard Garden Hose` / `Expanding Hose` (if the source URL says *Expandable*) / `Flat Hose`
/ `Hose Nozzle` / `Pot` / `Hose Reel` / `Hose Hanger/Holder` as appropriate.

**7. Prelist category can stall on ambiguous titles.** A "Fireman's" nozzle got offered
`Collectibles > Firefighting & Rescue > Hoses & Nozzles` as the first suggestion; the
extension took it and eBay then refused to advance ("None selected"). Fix by picking the
Watering Equipment category by hand (`caty=181015`), clearing the catalog-match and condition
dialogs — the extension then resumes on its own. This is a **separate, still-open bug** from
the description one.

## Recording a completed listing — schema gotcha

`listing_jobs` has **no `listing_id` column**. PATCHing `ebay_item_id` or `listing_id` onto a
listing job is silently ignored. Real item IDs live in the **`ebay_listings`** table, and the
`mark-listed` endpoint requires `listing_id`. Use the scratchpad helper, which sets the job
`completed` and upserts the `ebay_listings` row:

```bash
python <scratchpad>/complete_job.py <JOB_ID> <ITEM_ID> <PRODUCT_ID> <PRICE>
```

If it is missing, recreate it: `UPDATE listing_jobs SET status='completed', completed_at=…,
message=…` plus an `INSERT`/`UPDATE` into `ebay_listings (product_id, listing_id, environment,
price, quantity, status, account_id, started_at)` with `status='scheduled'` and `started_at`
set to the job's `listing_schedule_at`.

Two rows were left with placeholder `MANUAL-SRC-…` ids from a bad `mark-listed` call and have
since been corrected — if you see any more of those, replace them with the real item id.

## Standing rules

- **Timezone:** stored schedules are **naive Eastern**; eBay's editor shows **PDT**.
  `PDT = ET − 3h`. Never "normalise" the stored values.
- **Never** open an eBay listing/prelist URL while any job is `running` — the shared
  `localStorage.autozs_ebay_workflow` key hijacks it and corrupts the other job. Clear it with
  `Object.keys(localStorage).filter(k=>k.startsWith('autozs')).forEach(k=>localStorage.removeItem(k))`
  before opening a draft.
- **Never trust `listing_jobs.ebay_draft_id`** — the ids are scrambled by concurrent runs.
  Match drafts to products **by title** on https://www.ebay.com/sh/lst/drafts.
- **Verify the draft is the right product** (title, price, MPN) before editing anything.
- Only mark a job completed against a **real eBay item ID** from the confirmation dialog.

## Still open (do not claim these are fixed)

- The extension cannot write the description unattended. `enableHtmlCodeMode()` appears to
  fail inside the extension, upstream of the ordering fix that shipped in `bfa04ac`. Two
  theories were tested and **both disproven**: background-tab throttling (a foregrounded run
  failed identically) and an exact-length verification mismatch.
- Prelist category mis-selection on ambiguous titles (item 7 above).
- The re-fill Brand/date reset (item 3 above) — this one will publish bad data on any
  unattended run, so it matters before automation is turned back on.
- Scraped descriptions contain Home Depot nav junk ("Truck & Tool Rental", "Military Discount
  Benefit") on every listing including the ~56 already live. Fix in the importer, not per
  listing.
