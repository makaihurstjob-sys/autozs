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

