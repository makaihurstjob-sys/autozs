# Fixed batch continuation

Batch: `tmp/verified-ready-batch-2026-09-07.json`, 90 products, 82 eligible and 8 intentionally excluded. Database: `C:/AutoZS/data/autozs.db`; API: `http://127.0.0.1:8000`; Chrome CDP: port 9225. AutoZS extension ID: `ainpidpkelkbggebjijlcmmdcdgoggpg`.

Do not modify Master Dashboard deployment. Existing broad repository changes predate this continuation; preserve them.

## Verified this session

- Product 104 / job 312 scheduled successfully as eBay item 800629014040. Seller Hub scheduled row and editor confirmation captured in `continued-scheduled-after-hose.json` and `hose-confirmation.json`.
- It initially had Brand Unbranded despite package Husky. Revised the same item to Husky using its Seller Hub Edit link; eBay confirmed revision. Evidence: `hose-revised-confirmation.json` (title, item ID, and Brand Husky).
- Seven products without jobs have actual supplier blockers: 253 and 121 lack prices; 245, 244, 210, 205, 202 are not available for delivery (in_stock false, shipping -1). Do not enqueue by bypassing source checks.
- Product 142 / job 289 held needs_review: supplied Brand `.N/A` requires real brand verification. Do not blindly replace a known brand with Unbranded.
- Duplicate-title comparison across active listings pages 1 and 2 plus scheduled listings found no matches for the remaining failed jobs. Evidence: `continued-active.json`, `continued-active-page2.json`, `continued-scheduled-after-hose.json`.

## Extension fixes

- Exact nonempty committed-value comparisons; exclude dropdown search inputs and extracted-attribute selectors.
- Row values read only `button[name^="attributes."]`, excluding Suggested buttons. The Melnor draft had a blank Type trigger plus a visible Suggested Adapter button; old logic called that filled.
- Scoped dropdown selection uses the row trigger's aria-controls panel, preserving supplied brands. Known brands no longer validate as Unbranded; repair uses the supplied brand.
- Required specifics are repaired after photo uploads. Reveal Item specifics by scrolling its heading into view before repair/final checks, because eBay unmounts the controls when the worker scrolls down.
- Validation fails on empty required rows and on a mounted section heading with no controls, before eBay displays its own validation error.

Tests: ebay-fill.test.js and specifics regression/row/visibility tests passed. Last change restricting row-value buttons is covered by the suggestion regression.

## In progress

Product 166 / job 295 is the second full-workflow canary. First attempt confirmed Brand Melnor but failed Type; that exposed the Suggested Adapter false positive and virtualized controls. Latest retry uses both corrections. Check API state and live editor confirmation before releasing the other 11 retries (278, 288, 285, 290, 303, 299, 297, 305, 306, 311, 313).

Automation pause is false. Only canary 295 was requeued after final fixes. Do not open additional eBay tabs or reload the extension while a job is running. Use `tmp/cdp-read.mjs` to inspect the existing runner read-only. All eBay screenshots/text in tmp are time-specific evidence, not permanently current facts.
