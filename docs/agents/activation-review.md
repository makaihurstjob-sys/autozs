# Integration verification and activation review

Date: September 11, 2026. Base: `7885760`. Worktree: `C:/AutoZS/worktrees/activation-review-20260911`.
Scope: independent source/handoff review only. No tests, operational API/database, browser, environment files, service changes, or activation were performed by this reviewer.

## Readiness

Inventory account scoping, bounded delivery trial, and uncertain posting guards are present in this base. Restock guards are being finished separately and must be reviewed/integrated before the combined verification below. Historical evidence is 124 combined backend tests, nine posting test files, and ten mocked delivery-worker tests passing; these are recorded prior runs, not executions on the final restock integration.

No blocking conflict was identified between the three integrated tracks during this review. This is not clearance of the pending restock diff, which has its own independent reviewer. Live validation remains outstanding for account-correct replacement, actual stock restoration, schedule persistence/submission, and the full delivery cart cycle.

## Exact combined checks

Run in the coordinator's isolated integration checkout after serial integration, with no `.env` or operational database copied into it:

```powershell
C:/AutoZS/venv/Scripts/python.exe -m pytest apps/api/tests/test_ebay_orders.py apps/api/tests/test_ebay_revisions.py apps/api/tests/test_delivery_checks.py apps/api/tests/test_delivery_quotes.py apps/api/tests/test_listing_jobs.py -q --disable-warnings
node --test tools/delivery-check-extension/background.test.js
node tools/chrome-extension/ebay-submission-attempt.test.js
node tools/chrome-extension/ebay-fill.test.js
node tools/chrome-extension/background.test.js
node tools/chrome-extension/ebay-schedule-refresh.test.js
node tools/chrome-extension/ebay-schedule-field.test.js
node tools/chrome-extension/ebay-specifics-regression.test.js
node tools/chrome-extension/ebay-specifics-visibility.test.js
node tools/chrome-extension/ebay-specifics-search.test.js
node tools/chrome-extension/ebay-specifics-row.test.js
node tools/chrome-extension/ebay-revision-upload.test.js
node --check tools/chrome-extension/ebay-fill.js
node --check tools/chrome-extension/background.js
git diff --check
```

The revision-upload test is relevant to the restock execution boundary. The uploader awaits a successful batch `uploading` status response immediately before `upload.click()`; `patchBatch` throws on a failed API response. Backend upload-transition tests must exercise stale/excluded restocks at that boundary. Existing uploader tests use fake DOM/VM/browser calls and alone do not establish new backend rejection behavior.

`apps/api/tests/conftest.py` sets `DATABASE_URL=sqlite:///:memory:` before application imports and supplies disposable in-memory sessions; direct revision sessions also use in-memory SQLite. No root `.env`, API `.env`, or `dev.db` exists in this review checkout. Do not use tracked database sidecars. Startup disables report, source-refresh, traffic and push loops for memory databases. The heartbeat still runs against the memory database and invokes sold replacement reconciliation: saying all background work is disabled would be inaccurate. The settings class reads `.env` relative to the process directory, so run from the verified isolated checkout.

## Coordinator-only activation prerequisites

1. Reconcile the canonical board, preserve operational edits and runtime sidecars, review the final diff, and record the tested integration commit. Worktree commits are not deployed merely because tests pass.
2. Establish exclusive ownership of AUTOZS API/service and both relevant Chrome profiles. Inspect current listing/revision/delivery jobs, browser tabs and persisted workflow state before reload/restart. A prior idle check is not current evidence. Identify the actual service and extension package paths from the operational setup before applying its existing activation process. Never change or restart Master Dashboard deployment.
3. Activate the reviewed backend while idle through the existing AUTOZS operational process; verify health and the newly supported policy schema. Reload the posting extension only when idle and verify the packaged guarded source. Preserve storage: submission markers are the recovery record. Activation evidence must include versions/readback, separate from marketplace success.
4. Posting: use one coordinated runner in the verified account/profile. Unresolved attempts need eBay outcome evidence before recovery; there is no automatic negative-outcome reset UI. Storage clearing, another profile, or concurrent tabs can bypass the local protection. Verify schedule correction persisted to AUTOZS and confirmation reconciliation on a controlled authorized run. A successful submit click is not proof of an accepted listing.
5. Inventory: verify the sale account, eligible ended listing, current supplier price/availability/freshness and exclusions. Inspect existing active listings and open replacement/revision jobs before any controlled recovery. Observe both accepted marketplace result and account-correct backend state. Sequential idempotency tests do not establish a cross-process transactional lock.
6. Delivery: follow `docs/agents/delivery-implementation.md`'s reviewed sequence. Preserve postal codes, keep broad `enabled` false, use one exact eligible supplier-product ID and ZIP, verify signed-out empty dedicated cart and accessible product, then enable only that trial. Historical Home Depot errors must be rechecked. A held/exhausted job has no reset API; do not edit DB rows as a shortcut.
7. Observe add-one, destination, stable quote, remove, empty cart, completed matching job/quote, and cleared worker state. Stop the trial with `enabled: false, trial: null` and read it back. The trial is target-bounded, not one-shot: explicitly end it. Revocation blocks API leases but cannot cancel an in-flight browser action. Paid quotes still block listing eligibility, and API completion alone is not cart evidence.

Missing live evidence is a validation gap, not a claim that the supplier is currently down or a request for renewed blanket authorization. Coordinator must resolve real resource conflicts or missing target information before the dependent action.
