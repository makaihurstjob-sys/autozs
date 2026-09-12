# Initial ZIP availability filter

Base: `4df30b8`. Assignment: use buyer ZIP `84532` as the initial Home Depot delivery filter; inspect existing-listing support without confusing unknown results with confirmed unavailability. No operational resource access or application changes were performed.

## Existing configuration

The existing API supports `PUT /delivery-quotes/policy` with `{"enabled":true,"postal_codes":["84532"]}`. On this integration base, `trial:null` may also be supplied. Coordinator reports the older operational version lacks trial support, so the common two fields are sufficient. Read the policy back after writing it.

`coverage_reason` in `apps/api/app/services/delivery_checks.py` blocks Home Depot prelisting eligibility unless each configured ZIP has a matching-product, completed, quantity-one cart check less than 24 hours old with zero delivery charge. Missing checks, transient errors, unavailability failures, expired checks and paid delivery do not pass. This only establishes one destination's evidence, never nationwide availability. Amazon and other suppliers are not covered by this Home Depot policy. A disabled policy with a bounded trial collects evidence but does not enable the coverage gate.

The policy can start worker polling immediately. Before activation, the coordinator must verify exclusive ownership of the dedicated delivery profile, signed-out empty cart, and no unresolved worker state. Keep it distinct from a fulfillment checkout profile. `tools/delivery-check-extension/background.js` refuses existing Home Depot tabs before claiming and validates its lease before browser actions, but these safeguards do not replace verifying profile ownership. Never clear paused worker storage blindly or manually claim a job just to inspect it.

## Existing listing limitation

`claim_check` enrolls products from queued/needs_review/paused ListingJobs. `ensure_checks` accepts draft/monitoring products, and some published products may still be monitoring, but there is no public endpoint to explicitly enroll an existing product for an audit. Current failures only become queued or needs_review; they carry a message rather than a structured, verified regional-unavailable result. Neither delivery service queues an existing eBay listing withdrawal.

Therefore this policy does not filter or remove already live listings. Do not set global supplier stock false or withdraw listings based on a generic worker failure. Known mulch unavailability requires a separately verified coordinator action on its exact listing/account.

The smallest followup for an existing-listing audit is an explicit product-selection endpoint reusing `ensure_checks`, with policy ZIP scope and no listing mutation. Actual automatic filtering also needs structured available/unavailable/unknown evidence tied to supplier identity and destination, affirmative negative capture in the browser, and a regional hold reason respected by restoration/replacement paths. Transient page/network/cart failures must remain unknown. That cross-layer behavior is larger than this delivery-service assignment and was reported instead of implemented speculatively.

## Validation

Fixtures inspected: `apps/api/tests/conftest.py` forces in-memory SQLite and overrides request sessions; this worktree has no `.env` or `apps/api/.env`. No live database or browser was used.

`C:/AutoZS/venv/Scripts/python.exe -m pytest apps/api/tests/test_delivery_checks.py apps/api/tests/test_delivery_quotes.py -q --disable-warnings`

Result: **21 passed**, 975 existing warnings, 10.56 seconds. Tests exercise coverage, mismatched evidence, paid quotes, stale identity/age, retries and policy revocation. This verifies the integration base, not the older running service or a live supplier cycle.
