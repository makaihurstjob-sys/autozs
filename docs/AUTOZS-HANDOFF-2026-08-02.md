# AutoZS handoff — 2026-08-02

Continuation notes. Branch `codex/autozs-workflow-checkpoint`, all work pushed
through **45b8b76**.

## The immediate goal

Grind the eBay listing-job queue from **40 → 30** `needs_review` jobs by
finishing listings by hand. Zero were completed in the last session — see the
blocker below, which must be solved first or every attempt fails the same way.

Queue as of this writing:

| Count | Cause |
|---:|---|
| 27 | "eBay requires a description and AutoZS could not write one" |
| 8 | fields partially filled (11/14 groups) |
| 5 | prelist category stall |

Automation is **PAUSED** (`GET/POST /listing-jobs/automation-pause`, reason
"category stall; manual completion"). Leave it paused while working by hand, or
the runner fights you for the same drafts.

## BLOCKER 1 — eBay never receives the description

Worked live on job 55 (product 53, draft `5189958888020`). The description field
**displays** all 3,397 characters while eBay's validator still reports
**"A description is required."** The value is never reaching eBay's model.

Four approaches tried, all fail the same way:

1. Native `HTMLTextAreaElement` value setter + `input`/`change` events
2. `document.execCommand('insertText', …)` after focus+select
3. Setting the value, then a **real** keystroke (CDP click + type) so React's
   `onChange` reads the whole field
4. Writing with HTML mode on, then toggling off to commit — **the toggle wipes
   the field back to 0**

So `.claude/skills/autozs-ebay-editor/SKILL.md`'s claim that "only the raw
textarea write persists" **no longer holds** on the current editor. Treat that
section as stale.

### The one real discovery — likely the root cause of the 27

The "Show HTML Code" toggle only responds to **`label.click()`**.

```js
const box = [...document.querySelectorAll('input[type=checkbox]')]
  .find(c => /descriptionEditorMode/.test(c.id || ''));
const label = document.querySelector(`label[for="${CSS.escape(box.id)}"]`);
box.click();    // returns cleanly, checked stays false, NOTHING happens
label.click();  // actually flips HTML mode on
```

`ebay-fill.js` almost certainly clicks the input. If HTML mode never engages,
the raw textarea is inert and the write goes nowhere — which surfaces to the
user as "could not write the description". **Fix this first**, then re-test one
job unattended before doing anything by hand.

Note the checkbox and the textarea share an id prefix
(`…@DESCRIPTION-1-34-@rich-tex…`), so `getElementById` on the label's `for` can
return the wrong element. Match on `/descriptionEditorMode/`.

## BLOCKER 2 — drafts have no photos (newly found, not yet investigated)

Draft `5189958888020` contained **zero product images** — the only eBay-hosted
image was a USPS carrier icon. Meanwhile the job reports `image_count: 11`,
`local_image_count: 11`, `image_upload_status: "ready"`.

Even with a working description this listing could not go live. This is probably
true of the other 26 and may be *masked* by the description error firing first.
**Verify photo upload before assuming the description is the only problem.**

## What did work on job 55

Category resolved (`caty=159406`), draft created, price `$12.53`, required
specifics auto-filled (Type "Potting Soil", Brand "Unbranded" — the package says
**Vigoro**, so brand filling picks the wrong value), and the schedule was
**correct**: `08/13/2026 6:00 PM` Pacific = `21:00` Eastern, matching
`listing_schedule_at`. Do not "fix" the schedule — ET is stored, eBay shows PT.

Useful: `GET /products/{id}/ebay-package` returns title, price, condition,
`description` (full HTML), `item_specifics`, and `image_urls` — everything
needed to finish a listing by hand. eBay pages *can* reach the API directly.

## Environment gotchas that cost hours

- **The API runs without `--reload`.** Code changes need a real restart or it
  silently serves stale data (Amazon showed as a disabled supplier for hours).
- **Chrome can run a STALE cached service worker.** Content scripts pick up edits
  while `background.js` does not; the symptom is extension messaging answering
  *nothing* ("message port closed"), which reads like a dead worker even though
  it is healthy and polling. `Launch-AutoZS-Test-Chrome.ps1` now clears
  `<profile>\Default\Service Worker` on every start. **That launcher lives at
  `C:\AutoZS\`, outside the repo, so it is not version-controlled.**
- Diagnostic trick: request a distinctive 404 like `/__probe/<label>/<value>` —
  uvicorn logs 404s, giving a zero-code channel out of the service worker.
- PowerShell here-strings break on embedded double quotes; use `git commit -F`.

## Depop / Amazon side (done, for context)

Amazon import is hands-free: one click gives 6 variations, 34 photos, 28 review
photos auto-attributed, in ~2s. Key facts in
`~/.claude/.../memory/autozs-amazon-depop-capture.md`:
`data-asin` on review thumbnails is a decoy (it is the *viewed* variation);
`data-reviewid` is the real join key; the signed-in reviews page gives 28 fully
attributed photos vs 12 partly attributable from the carousel.

Open Depop items: variants need a price (all `$0`), Brown/Lake Blue/White have no
photos yet, no Depop account exists yet (Settings → Depop, needs the username),
and the photo review still lives on its own page rather than inside the draft.

## Price approvals

Two approved and confirmed live by eBay ($30.53 Melnor, $81.53 Hydrotech); two
rejected. **Rejections do not stick** — a later repricing run regenerates the
same proposal (#177 and #189 came back). Worth fixing. Also watch #180, which
proposed a $26 cut with *no* source-price change.
