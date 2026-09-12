# Replacement publication freshness

Base: 4df30b8. Worktree: C:/AutoZS/worktrees/publish-freshness-20260911.

Automatic sale replacement and zero-view rotation previously trusted SupplierProduct.updated_at. A metadata-only refresh could therefore allow a new publication with missing or obsolete stock, price, or shipping evidence. Both gates now require all three actual observation timestamps within the inclusive preceding 24 hours and reject future timestamps. Rotation orders candidates by stock observation time. Account-scoped sale duplicate checks remain unchanged.

Regression matrix exercises both publication paths, each observation independently, missing evidence, evidence 25 hours old, future evidence, and the inclusive 24-hour boundary. Fresh observations remain eligible with an old metadata timestamp. Existing positive sale and listing-job fixtures now explicitly capture stock rather than relying on a default inferred stock state.

Before implementation the new 24-case matrix produced 18 failures and 6 positive controls. Tests use the existing in-memory SQLite fixture and mocked readiness/package checks for rotation. No live database, environment file, browser, server, or marketplace actions were used.

Validation (DATABASE_URL=sqlite:///:memory:, C:/AutoZS/venv/Scripts/python.exe):

- `-m pytest apps/api/tests/test_publish_freshness.py -q --tb=short --disable-warnings`: 24 passed in 11.96 seconds.
- `-m pytest apps/api/tests/test_ebay_orders.py apps/api/tests/test_listing_jobs.py -q --tb=short --disable-warnings`: 69 passed in 60.12 seconds, including existing cross-account replacement coverage.
- Existing datetime/pytest deprecation warnings; `git diff --check` clean.

Limitation: these checks control queue creation. They do not constitute live marketplace validation or a universal final-submit eligibility check. Explicit timestamps can only be as trustworthy as upstream capture evidence; detector hardening is a separate assignment.
