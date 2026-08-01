# AutoZS handoff — rev 3

_Updated 2026-08-01, after the Aug 2 / Aug 3 push. Everything below is verified live unless marked otherwise._

A paste-ready copy for a fresh session lives at `C:\Users\macor\Documents\AutoZS-Handoff-Prompt.txt`.

Continue the AutoZS eBay listing work. Full runbook is at
C:\AutoZS\repo\docs\AUTOZS-HANDOFF-2026-07-31.md -- read it first. This file is
the current state plus the things that cost the most time to learn.


CURRENT STATE
-------------
- Outstanding listing jobs: 52. (Count them with the snippet at the bottom.)
- eBay scheduled per day:  Aug 2 = 7/7 DONE, Aug 3 = 7/7 DONE,
                           Aug 4 = 4/7, Aug 5 = 3/7, Aug 6 = 3/7.
- GOAL: 7 listings per day scheduled on eBay from Aug 2 onward. Aug 1 stays at 5
  (the user explicitly chose that; it was the original plan for today).
- AUTOMATION IS PAUSED. Resume only when you are done:
    curl -s -X POST http://127.0.0.1:8000/listing-jobs/automation-pause \
      -H "Content-Type: application/json" -d '{"paused": false}'
- Jobs already assigned to the remaining free eBay slots: 108 (Aug 4 8:00pm ET),
  109 (Aug 4 8:40pm), 110 (Aug 4 9:00pm), 111/112/113/114 (Aug 5),
  115/116/117/118 (Aug 6). Job 103 (Rhino watering can) is a known repeat
  failure -- skip it.
- Job 108 is HALF DONE: draft 5185459731723 has 13/13 photos, price $155.53,
  time 5:00 PM PDT (= 8:00 PM ET, correct). It still needs Type fixed
  (shows "Amphora (+1)"), Brand -> Veikous, date -> Aug 4, and the description.
- After Aug 4-6 are at 7/7 the queue lands around 41.


THE FOUR THINGS THAT ACTUALLY MATTER
------------------------------------

1. DESCRIPTION -- this recipe works every time, ~15 listings in a row.
   eBay validates its RICH editor, not the HTML source box. Writing the textarea
   alone passes your own verification and is then rejected on submit.

     a. Click the "Show HTML Code" LABEL -- NOT the checkbox input.
        Clicking the input flips the DOM but React never sees it and the content
        is discarded. This one detail wasted hours.
     b. Write the raw textarea through the native value setter:
          Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value')
            .set.call(ta, html);
          ta.dispatchEvent(new Event('input',{bubbles:true}));
          ta.dispatchEvent(new Event('change',{bubbles:true}));
          ta.dispatchEvent(new Event('blur',{bubbles:true}));
     c. Wait ~2.5s, confirm ta.value.length matches.
     d. Click the LABEL again to switch HTML mode OFF. That is what commits it.
     e. Confirm the rich editor is non-empty:
          document.getElementById('se-rte-frame__summary')
            .contentDocument.querySelector('[contenteditable="true"]').innerHTML.length
   eBay normalises ~10 characters of whitespace (3272 -> 3262). That is fine.
   WRITE THE DESCRIPTION LAST, right before submit -- a calendar or HTML-mode
   re-render silently wipes it.

2. TIME/HOUR FIELDS -- the <select> elements are HIDDEN (zero-size).
   eBay renders its own dropdown on top and ignores the native select, so
   form_input sets it, your check reads it back correctly, and eBay reverts it on
   submit. It will even report "revised" while keeping the old time.
   FIX: click the VISIBLE control and pick the option from the rendered list.
   Since switching to that, every submit has landed on the intended slot.
   ALWAYS re-verify the time immediately before clicking List it.

3. TIMEZONES. Stored schedules are naive EASTERN. eBay's editor shows PDT.
   PDT = ET - 3h.  7:00 PM ET = 4:00 PM PDT. Never "normalise" stored values.

4. PHOTOS. file_upload is sandboxed and cannot read C:\AutoZS\repo\downloads.
   Replicate what the extension does -- fetch from the API in page context and
   inject via DataTransfer:
     fetch('http://127.0.0.1:8000/' + localPath) -> blob -> new File(...)
     input.files = dataTransfer.files; dispatch input + change.
   If photos end up duplicated, eBay exposes per-tile aria-label="Delete photo N"
   buttons, so deduping is scriptable.


WHAT IS FIXED vs STILL BROKEN
-----------------------------
FIXED and verified:
  59666d2  Stop reopening runners that are actively reporting progress.
           THE churn bug. reopenOrphanedListingJob decided purely on "is there a
           tab" and reopened runners that had just sent a liveness ping. Every
           reopen restarts the workflow from the top and the description step is
           near the END, so it never survived. Verified: 3 reopens before the
           fix, 0 after.
  0819c55  ebay_sync stores started_at as Eastern, not UTC. It was writing naive
           UTC while everything else is naive Eastern, so synced listings sat ~4h
           ahead and rendered on the wrong calendar day.
  7a882e5 / 14f633b / 9a90244  the three description commits (commit-to-rich,
           wait for lazy render, foreground runner tabs).

STILL BROKEN -- this is the next thing to fix:
  PRELIST CATEGORY STALL. "eBay prelist stalled: Selected a suggested category,
  but eBay did not continue after Done."
  Cause: prelistCategoryScore picks the suggestion with the best title-token
  overlap. For a "Wood Raised Garden Bed Elevated" eBay offers
    1. Plant Care, Soil & Accessories > Baskets, Pots, Window Boxes & Saucers  <- correct
    2. Garden Structures & Shade > Awnings & Canopies
    3. Garden Structures & Shade > Gazebos & Pergolas
  and the scorer favours 2 or 3 on the words Wood/Garden/Elevated. Those are not
  leaf categories, so Done never advances. Same thing happened on a "Fireman's"
  nozzle, which got offered Collectibles > Firefighting & Rescue first.
  Code: ebay-fill.js around line 2040 (prelistCategoryScore / the Done click).
  Likely fix: prefer eBay's FIRST suggestion, and/or verify the Done button is
  enabled and that the chosen category is a leaf before clicking.
  Manual workaround: click "None selected" -> pick the right suggestion ->
  "Continue without match" -> condition New -> "Continue to listing".

UNVERIFIED: the description fixes have STILL never had a clean unattended run.
The churn fix removed one blocker; the category stall then ended the test before
the description was reached. Do NOT claim the description is fixed in automation
until one job completes end to end on its own.


TRAPS THAT HAVE ALREADY CAUSED REAL DAMAGE
------------------------------------------
- NEVER trust listing_jobs.ebay_draft_id. The ids get scrambled by concurrent
  runs -- job 83 held job 74's draft, jobs 75 and 76 held each other's. Match
  drafts to products BY TITLE on https://www.ebay.com/sh/lst/drafts.
- ebay_listings gets duplicate rows for one real item. When deduping, verify the
  real owner by PRICE + TITLE against eBay. I once kept the lower row id and it
  was the wrong product (item 800437436602 is a $21.53 nozzle, not Vigoro rose
  food) -- that briefly detached a live listing from its job.
- 10 listings PUBLISHED EARLY instead of holding for their date (jobs 79, 80, 81,
  82, 86, 88, 89, 90, 95, 96). Mechanism: a re-fill resets the schedule date to
  TODAY, and with today's time already past, eBay lists immediately. Always
  re-check the date after any re-fill.
- Re-running the assistant fill also resets Brand to "Unbranded".
- autozs_autosubmit=1 can publish mid-edit. Job 94 went live as "Unbranded"
  before I finished. Drop autosubmit from the URL when finishing by hand.
- The AutoZS overlay can swallow the "List it" click with no error and no
  confirmation. Check for "AutoZS in progress" before submitting.
- Never open an eBay listing/prelist URL while a job is running, and clear the
  workflow key first:
    Object.keys(localStorage).filter(k=>k.startsWith('autozs')).forEach(k=>localStorage.removeItem(k))
- listing_jobs has NO listing_id column. Real item ids live in ebay_listings.
  Record completions with the scratchpad helper complete_job.py
  (JOB_ID ITEM_ID PRODUCT_ID PRICE).
- Type dropdown: selecting a new value ADDS rather than replaces, and clicking a
  value under "Selected" to deselect is unreliable. Use the dropdown's "Clear"
  link, then add the one you want. Common wrong defaults: Coil Hose for hoses,
  Cleaning Gun Nozzle for nozzles, Amphora for planters and raised beds.


PER-LISTING LOOP (~6-10 steps once you have the rhythm)
------------------------------------------------------
 1. curl -s "http://127.0.0.1:8000/listing-jobs/<ID>"   (assistant_url, schedule)
 2. Clear the autozs localStorage keys, then open the assistant_url WITHOUT
    autozs_autosubmit. Let the extension build the draft -- it gets category,
    price, photos and specifics right. It will fail on the description; expected.
 3. If it stalls on category, do the manual workaround above.
 4. Reload the draft cleanly: /lstng?draftId=<DRAFT>&mode=AddItem
 5. VERIFY IT IS THE RIGHT PRODUCT (title, price, MPN) before editing anything.
 6. Fix Type / Brand (real eBay brands beat custom values -- "Luster Leaf",
    "Best Choice Products" both exist).
 7. Set the date with the calendar picker; set the time with the VISIBLE dropdown.
 8. Photos -- inject via the API-fetch method if the count is 0.
 9. Description LAST, per the recipe above.
10. Re-verify time + date, confirm no AutoZS overlay, then click List it.
11. Capture ID-<item> and record it with complete_job.py.

Queue count:
python -c "import sqlite3;c=sqlite3.connect(r'C:\AutoZS\data\autozs.db');print(c.execute(\"SELECT count(*) FROM listing_jobs WHERE status IN ('needs_review','queued','ready_to_save')\").fetchone()[0])"

Per-day eBay check:
python -c "import sqlite3;c=sqlite3.connect(r'C:\AutoZS\data\autozs.db');[print(r) for r in c.execute(\"SELECT date(started_at),count(*) FROM ebay_listings WHERE status='scheduled' GROUP BY 1 ORDER BY 1\")]"

After this, the user wants to move on to DEPOP (not "depot" -- that was a typo).
