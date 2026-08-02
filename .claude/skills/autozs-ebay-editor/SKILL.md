---
name: autozs-ebay-editor
description: Verified DOM landmarks and filling rules for eBay's listing editor, used by the AutoZS Chrome extension (tools/chrome-extension/ebay-fill.js) - item specifics, description HTML mode, schedule controls, submit confirmation, and the Eastern/Pacific time convention. Use when editing or debugging the extension's field filling, verification, or submission logic.
---

# eBay listing editor: verified landmarks

Every selector here was confirmed against the live editor. eBay's markup does **not** match the obvious guesses, and wrong guesses have silently produced blank fields for months. When adding a new field, probe the real DOM before writing selectors.

## Item specifics

```js
// One row
button[id*="item-specific-dropdown-label"]        // the label (class "fake-link" - an info link, NOT the dropdown)
label.closest("div")                               // wrapper; has class "required-field" when mandatory
labelDiv.nextElementSibling                        // the value host: holds the trigger + chosen values
```

- Requirement level also appears in sibling span ids as `[ESSENTIAL]` vs `[OPTIONAL]`.
- The chosen value renders as a **button** inside the value host (skip one labelled `Clear`), not as an input value.
- Opening the trigger sets `aria-expanded="true"` and names its panel via **`aria-controls`**; read options from `document.getElementById(trigger.getAttribute("aria-controls"))`.
- Options are **`role="menuitemcheckbox"`** (`div.filter-menu__item`), inside `div[role="menu"].filter-menu__items`.

**Do not query options document-wide.** The older code searched `[role=option],[role=menuitem],[role=menuitemradio],li` across the page: it matched **zero** real options and could click the description font menu ("Arial", "14", "B") into a specifics field. Always scope to the `aria-controls` panel.

Preference order when filling: value supplied by the package → an option marked "Recommended" → an option matching product-title words → first valid option. Multi-select menus stay open; close the trigger before moving to the next row.

## Description

- Toggle: checkbox whose label reads **"Show HTML Code"**; find via `label[for=...]` (ids contain `@`, so use `CSS.escape`).
- Raw editor appears only after toggling: `textarea[id*="rawEditor"]`.
- WYSIWYG body: `iframe[id*="se-rte-frame"]`.

**Every candidate target toggles the same checkbox.** Clicking a list of candidates in sequence flips HTML mode straight back off when eBay re-renders slowly — that is the long-standing "description needs manual pasting" bug. Click once, wait for the source field, and if the checkbox already reads checked, only wait.

**Both writes are needed** (settled live 2026-08-02 on draft `5189958888020`, verified by a `Save for later` → reload round-trip):

1. Toggle HTML mode on, write `textarea[id*="rawEditor"]` via the native `HTMLTextAreaElement` value setter plus `input`+`change`.
2. Toggle HTML mode back off.
3. Write the `div[contenteditable="true"]` inside `iframe#se-rte-frame__summary` with `execCommand("insertHTML")`.

**Toggling HTML mode off does NOT parse the source box into the rich editor.** eBay only syncs its own model on a real edit, so after the toggle the raw textarea still reads 3397 chars while the rich editor reads 0. Gating success on `richDescriptionLength() > 0` after a plain toggle-off therefore reports failure for a description that was written fine — that was the real cause of the 26 "AutoZS could not write one" jobs, not the toggle itself. Step 3 is what fills the rich side.

`execCommand("insertHTML")` into the contenteditable **does persist** through eBay's server: after save+reload the raw textarea and the rich editor both come back populated. The earlier claim that eBay wipes it was a measurement artifact.

Do not judge success by the editor's `placeholder` class — it is inert CSS and stays on the element even when the editor is full.

eBay rejects submission outright when the description is empty (`"A description is required."`), so verify it right before submitting, not only at fill time.

## Schedule

Controls are native **`<select>`** elements, not buttons:

- `select[name="localizedStartHours"]`
- minutes select — **generated name**, cannot be matched by name
- `select[name="meridian"]`
- `input[name="scheduleStartDate"]` (typing is unreliable; the calendar picker works)

Scope the select search to the schedule panel (walk up from the day field to the nearest ancestor holding ≥2 selects). A document-wide "numeric select" search can bind minutes to an unrelated control such as quantity. Set values with the native `HTMLSelectElement` value setter plus `input`+`change` events.

### Time convention (do not change without asking)

`listing_schedule_at` holds **naive Eastern wall time** (the seller works in ET; eBay displays Pacific). `parseListingSchedule` interprets offset-less values as `America/New_York`; values carrying an explicit offset are honored as written. Reading them as UTC puts listings live four hours early — that really happened. Never normalize the stored values themselves.

## Submitting

A vanished List button is **not** proof of submission. Require a real publish confirmation, or navigation away from the editor; otherwise report failure honestly — the item is still a draft. When unconfirmed, capture what eBay showed (validation banner, innermost alert text, and any required specifics still blank) into the job message so the next failure explains itself.

When scraping error text, take only **innermost** matches and cap the length: `[class*="error" i]` matches wrapper elements that can span an entire page section, which produced review messages made of unrelated listing copy.

## Workflow state

`localStorage.autozs_ebay_workflow` is a **single shared key** across all ebay.com tabs. Two runner tabs corrupt each other. A resumed `create_draft` workflow must never act on a `mode=ReviseItem` page (it would pour one product's data into another's live listing).

## Testing

`node tools/chrome-extension/<name>.test.js` for each of ebay-fill, background, capture, popup, ebay-revision-upload. The harness is a shared `vm` context — if a test overwrites a global (`isVisible`, `waitForCondition`, `fetch`), **restore it**, or later tests fail in confusing ways.
