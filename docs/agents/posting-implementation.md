# Uncertain eBay submission guard

Base: 8355c1b. Assigned checkout: C:/AutoZS/worktrees/posting-fix-20260911.

Final scheduled submission now verifies durable extension storage before clicking. It records both the job and account/product identities, reads the marker back, and saves confirmation-pending workflow state. A storage error prevents the click. The final action calls the button once; it does not use the prelisting helper whose timeout fallback can click again.

An unconfirmed response, unrelated navigation, or click exception leaves an unresolved attempt. Reentry, manual draft filling in that workflow, and orphan-runner reopening are held. The message no longer claims that an uncertain submission is still a draft or recommends retrying. Confirmation reconciles the marker only after AUTOZS mark-listed and job completion succeed. A confirmed job stays blocked, while a different replacement job for that account/product is allowed. A late old-job confirmation cannot clear a newer unresolved product attempt.

## Validation

All nine files passed with these commands from the assigned checkout:

```powershell
node tools/chrome-extension/ebay-submission-attempt.test.js
node tools/chrome-extension/ebay-fill.test.js
node tools/chrome-extension/background.test.js
node tools/chrome-extension/ebay-schedule-refresh.test.js
node tools/chrome-extension/ebay-schedule-field.test.js
node tools/chrome-extension/ebay-specifics-regression.test.js
node tools/chrome-extension/ebay-specifics-visibility.test.js
node tools/chrome-extension/ebay-specifics-search.test.js
node tools/chrome-extension/ebay-specifics-row.test.js
node --check tools/chrome-extension/ebay-fill.js
node --check tools/chrome-extension/background.js
git diff --check
```

Tests load source into Node VM contexts with fake DOM, in-memory storage, and mocked browser/network calls. They do not use an application database, credentials, or a live browser. New coverage checks one click despite no acknowledgement, restart/new-job holds, thrown clicks, unrelated navigation, failed and silently discarded storage writes, workflow persistence failure, confirmation tombstones, valid replacement eligibility, late confirmation, explicit URL identity, account isolation, startup/manual-fill holds, and background reopening holds. The final-click regression throws if the retrying prelisting helper is called.

## Operational limits and recovery

Persistence is chrome.storage.local in this extension profile, not backend durable history or a cross-device lock. Clearing extension storage or using another profile removes this protection. Storage check/set is not an atomic multi-tab lock; coordinated single-runner ownership remains required.

Unknown attempts intentionally remain held until evidence establishes the result. A matching eBay confirmation page goes through the existing confirmation reporter and completes reconciliation. Without that confirmation, the coordinator must investigate the actual eBay listing/draft outcome; this change does not add an automatic negative-outcome reset or a manual reset UI. Do not clear markers merely to retry. A failed write can conservatively leave a marker even if no click occurred.

No extension reload, listing submission, API mutation, or live validation was performed by this worker. Tests demonstrate mocked recovery behavior, not an accepted live eBay listing.
