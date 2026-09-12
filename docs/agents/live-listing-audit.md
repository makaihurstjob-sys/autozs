# Existing live listing delivery audit

Base: 4f3eafd. Worktree: C:/AutoZS/worktrees/live-listing-audit-20260912.

Resumed and completed the two existing uncommitted API/service edits. Added POST /delivery-quotes/audits/live-listings with an explicit account_id and 1-100 unique positive integer listing row IDs. Only active/live/listed production rows belonging to that account are enrolled. The service uses the existing enabled policy ZIP list (84532 when configured), refuses disabled/trial policies, and reports enrolled and skipped selections separately. It does not scan or enroll every account.

Enrollment reuses the existing supplier/ZIP queue identity. Fresh completions are reused; expired completions are requeued with obsolete completion/lease evidence cleared. Running leases, queued retries and needs_review holds remain intact. Unknown browser failures never change listing quantity/status, supplier stock, or relisting flags. No delisting or stock-revision action was added.

Validation:
- Confirmed worktree root and apps/api have no .env files. Existing conftest forces sqlite:///:memory: before importing application modules; background external loops are disabled for memory databases.
- New tests use their own memory SQLite sessions and minimal FastAPI router without production application lifespan. No browser/API/environment/database access to live resources.
- python -m pytest apps/api/tests/test_live_listing_audit.py -q: 14 passed.
- python -m pytest apps/api/tests/test_delivery_checks.py apps/api/tests/test_live_listing_audit.py -q --disable-warnings: 31 passed in 11.16s (existing deprecation warnings).
- git diff --check passed.

Coverage includes cross-account/sandbox/ended/nonselected exclusions, lease-preserving repeated enrollment, unknown failure holds and unchanged inventory, fresh/stale evidence, non-Home-Depot skip, disabled/trial rejection, API bounds/type validation and endpoint wiring.

Limitations and activation:
- Coordinator must integrate/activate and explicitly submit real account-scoped row IDs in batches of at most 100. No live listings were checked here.
- Existing eligibility requires draft/monitoring products and the first supplier source to be a valid Home Depot item; other products are reported skipped.
- Supplier/ZIP evidence is intentionally shared between listings of the same product; enrollment selection is account-scoped, supplier evidence is not account-specific.
- Sequential retry is idempotent; existing unique supplier/ZIP database constraint prevents duplicate records. Concurrent first-time enrollments retain the existing ensure_checks transaction behavior and may require caller retry after a uniqueness conflict.
- Missing evidence requires review or bounded existing retry; this endpoint does not automatically reset review holds or translate failures into unavailable stock. Confirmed removal decisions remain a separate coordinator workflow.
- This proves queue enrollment and mocked behavior, not deliverability to 84532 or nationwide availability.
