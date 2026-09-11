# Bounded delivery trial implementation

Base: `8355c1b`. Worktree: `C:/AutoZS/worktrees/delivery-trial-20260911`.

## Behavior

`PUT /delivery-quotes/policy` now accepts an optional `trial` containing one positive integer `supplier_product_id` and one five-digit ASCII `postal_code`. A trial requires `enabled: false` and an eligible Home Depot supplier belonging to a draft or monitoring product. Invalid scope is rejected before any policy or lease changes.

Example policy (replace the illustrative supplier ID with the reviewed target):

```json
{"enabled": false, "postal_codes": ["10001", "33101", "60601", "75201", "90001"], "trial": {"supplier_product_id": 123, "postal_code": "60601"}}
```

Claims enroll only the explicitly selected supplier and ZIP, including when no listing job exists. Older broad jobs remain unclaimed. The broad coverage gate remains disabled. Captured quotes still use the existing quote rules, including paid-delivery blocking; trial mode does not override those rules.

Omit `trial` or send `trial: null` with `enabled: false` to stop the trial. Changing or removing trial scope revokes affected running leases durably, moving uncertain jobs to `needs_review`. Old heartbeat, failure, and completion tokens remain invalid even after the same scope is re-enabled. Completed-response recovery remains available because it performs no new cart action. Switching to broad mode requires clearing the trial explicitly (legacy callers that omit it clear it automatically).

Existing retry limits and 24-hour freshness continue to apply within the single supplier/ZIP scope. This is bounded by target, not a one-shot time-limited authorization; coordinators should remove the trial after their controlled check. The browser may already have a cart action in flight when policy changes; revoke prevents further valid API leases and requires existing worker heartbeat checks. Cart inspection remains a coordinator responsibility.

## Validation

Fixtures inspected: `apps/api/tests/conftest.py` overrides DATABASE_URL and sessions to disposable in-memory SQLite. App startup disables operational schedulers/watchers for memory databases. Test imports use inline image data; no production environment file exists in this worktree. Extension tests use mocked browser and network APIs.

Backend command: `C:/AutoZS/venv/Scripts/python.exe -m pytest apps/api/tests/test_delivery_checks.py apps/api/tests/test_delivery_quotes.py apps/api/tests/test_listing_jobs.py -q --disable-warnings` — 65 passed (existing deprecation warnings).

Worker command: `node --test tools/delivery-check-extension/background.test.js` — 10 passed.

Six new backend regressions cover target/ZIP isolation against pre-existing broad jobs, disabled broad gate, independent enrollment, revocation/re-enable, switching product or ZIP, invalid configuration preserving the current lease, and explicit secondary supplier selection. Existing tests cover mismatched evidence, retries, paid quotes, freshness and broad scheduling.

No live browser, API, database, policy, extension activation, or service changes performed. Coordinator must integrate and activate separately; mocked checks do not prove a live Home Depot quote cycle.


## Independent continuation review

Reviewed implementation commit `6451015` against canonical assignment board. No blocking defect found in the requested single-supplier/ZIP trial or durable revocation paths. The six committed regressions cover target isolation, independent enrollment, disable/re-enable, product/ZIP switch, invalid policy preserving a lease, and explicit secondary supplier selection. Re-inspected the in-memory backend fixture and mocked worker harness; the previously recorded 65 backend and 10 worker passes are existing evidence, not new executions in this review. No redundant broad suite was run.

Coordinator activation sequence:

1. Integrate the backend commit, validate the combined tree, and activate AUTOZS through its existing operational process after idle checks. This change does not alter the delivery extension package. Inspect the deployed worker version before deciding whether a reload is necessary.
2. Read current `GET /delivery-quotes/policy` and `/delivery-quotes/jobs`, inspect the dedicated worker state and tabs, and establish exclusive ownership of the delivery guest profile. Do not proceed over an active or paused job or an unknown cart. Confirm policy is `enabled: false, trial: null` before browser inspection; preserve the existing `postal_codes` list.
3. Confirm a currently accessible Home Depot product and signed-out empty cart in the dedicated profile. The coordinator-only inspection helper supports `--inspect-cart` and `--inspect-product <exact URL>` on port 9335. Historical supplier errors require a fresh check. Its inspection mode refuses any existing worker state; a paused state needs explicit cart reconciliation, not blind storage clearing.
4. Select the exact supplier-product ID (not parent product ID) and five-digit destination ZIP. Confirm its parent product is draft/monitoring and inspect any existing job for that pair: a fresh completion will not rerun; needs_review or exhausted attempts will not auto-reset. There is no delivery-job retry/reset API in this implementation. Resolve an existing hold through a separately reviewed recovery action or choose another eligible target; do not edit live DB rows as a shortcut.
5. PUT the preserved policy with `enabled: false` and the exact trial object, then GET it back and verify both fields. Let the isolated worker claim naturally; a manual diagnostic claim would itself reserve a browser lease. Observe only the selected supplier/ZIP job running.
6. Verify the full quantity-one add, destination, stable quote, removal and empty-cart cycle, persisted completed job, and matching product quote. Confirm worker state is cleared and its owned tab closes. A paid quote is valid capture evidence but remains a listing blocker. An API completion alone does not replace browser/cart evidence.
7. End the controlled trial promptly by PUT with `enabled: false, trial: null` and the preserved ZIP list, and read policy back. On failure, revoke scope immediately and inspect the preserved cart/state before recovery. Revocation invalidates API leases durably but cannot cancel an already in-flight browser action. Never re-enable merely to resurrect the old token.

Remaining prerequisites are operational activation, fresh resource/cart/supplier checks, actual target ID/ZIP selection, and one successful live quote cycle. Broad coverage stays disabled. No live resource was accessed during this review.
