# Scoped listing cancellation — September 27, 2026

Base: 2fe39e5. Isolated branch fixes/restock-cancellation-20260927.

A cancelled duplicate publication previously excluded quantity restoration of the existing listing. ListingJob now stores cancellation_scope: product (conservative default, including legacy rows) or publication_only. PATCH /listing-jobs/{id} accepts the scope only together with explicit status=cancelled. The response exposes it in full and lite representations. Every cancellation without explicit scope returns to product scope. No message text is interpreted as permission.

Only stock_restoration_block opts into the narrower scope. Publishing, replacement creation, readiness and queue reactivation still honor the cancellation. Paused/deleted products, relist blocks (including sibling listings), supplier availability, valid price/shipping and observation freshness remain enforced.

Validation (DATABASE_URL=sqlite:///:memory:, PYTHONPATH=apps/api):
- python -m pytest apps/api/tests/test_listing_cancellation_scope.py apps/api/tests/test_supplier_freshness.py -q --tb=short --disable-warnings: 36 passed.
- python -m pytest apps/api/tests/test_ebay_revisions.py -k 'restock or stock_reductions' -q: 30 passed, 33 deselected.
- git diff --check: passed.
- Additive migration tested twice on a disposable legacy SQLite table; existing cancellation retained product scope.
Initial new-test fixture failures (missing settings table and shipping representation) were corrected; final targeted runs pass. Existing datetime/pytest deprecation warnings remain.

Not activated. No operational database, inventory, service, browser, or purchase changes. Product 95 remains unchanged. No direct eBay verification performed.

Integration follow-up: review operational changes and activation authorization before migration/restart. Re-read product 95's exact cancelled duplicate job and existing listing before explicitly changing that job to publication_only; never bulk-convert cancellations or infer scope from messages. Reassess current supplier evidence and all other guards. A passing unit test is not proof of live restoration. Keep the next-real-sale checkout reminder parked.
