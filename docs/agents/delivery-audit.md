# Delivery activation audit — September 11, 2026

Owner: delivery agent. Base: 23fcd18. Branch: agents/delivery-20260911.
Scope: code audit and this report only; no live operations or application edits.

## Highest-value next gap: bounded activation

The current policy cannot scope an end-to-end worker trial to one product while leaving broad listing coverage disabled. `apps/api/app/api/delivery_quotes.py:36` exposes only `enabled` and `postal_codes`. The same enabled switch controls coverage (`apps/api/app/services/delivery_checks.py:34`), job creation (`:56`), claims (`:87`), and heartbeat/completion validation (`:140`). Enabling claims automatically enrolls every eligible product with a queued, needs_review, or paused listing (`:91-95`), then claims from the eligible queue (`:108-130`). A single ZIP narrows destinations, not products.

This is a code-confirmed rollout limitation, not evidence of a current supplier outage. The historical handoff asks for one controlled product/ZIP cycle before broad activation, but the policy has no native trial scope. Manually manipulating jobs or temporarily enabling the global policy would not establish that isolation.

Recommended next implementation: add an explicit bounded trial scope (one supplier product and one ZIP) independently of broad coverage activation. Enforce scope at enrollment, claim, heartbeat and completion; removing the trial must revoke further actions. Preserve existing paid-quote blocking behavior. The coordinator should own the one live trial and its browser profile.

Acceptance tests, using disposable database fixtures and mocked Chrome:

- With broad coverage disabled and one trial configured, only the selected product/ZIP can be claimed; unrelated listing eligibility and job enrollment remain unchanged.
- Pre-existing queued jobs outside the trial cannot be claimed.
- Disabling/changing the trial rejects old heartbeats and completion before more browser actions.
- Trial completion persists quote evidence only after confirmed cart cleanup; restart/lost-response behavior still passes.
- Existing enabled-policy behavior and paid-quote blocking remain intact.

## Preconditions before a live trial

- Read current API policy, jobs and isolated extension state; historical values are not current verification.
- Confirm exclusive ownership of the dedicated guest profile and an empty signed-out cart; preserve unknown tabs/carts.
- Confirm the prepared extension package matches reviewed code and routes respond. No worker should reload shared browsers or services independently.
- Confirm a supplier product page currently loads. Past Home Depot errors do not establish present availability.
- Finish one add/ZIP/stable-quote/remove/empty-cart/persisted-completion cycle before expanding scope. Confirm exact product, quantity one and destination evidence; free sample ZIPs do not prove nationwide delivery.

Existing safeguards are visible in `tools/delivery-check-extension/background.js`: unknown tabs stop claims (`:36`), a heartbeat precedes subsequent browser work (`:49`), progress is saved before Add to Cart (`:77`), and removal is confirmed before completion (`:103-110`). `page.js:21-43` verifies guest state and cart identity; `delivery_checks.py:161-177` validates leased product/ZIP/quantity and records completion with the quote.

## Verification and limits

Inspected `tools/delivery-check-extension/background.test.js` before execution: its VM harness mocks fetch, Chrome APIs, storage and time; it reads only the local worker source and does not start a server or access a database.

Executed from the assigned worktree:

`node --test tools/delivery-check-extension/background.test.js`

Result: 10 passed, 0 failed. These cover isolated happy path, uncertain add, foreign tabs/carts, invalid lease, network recovery, lost completion response, bounded supplier retries and uncertain failure reporting. They do not validate real Home Depot selectors or the proposed trial scope. Backend tests were inspected but not executed. No live API, browser, credential, operational database or deployment was accessed.
