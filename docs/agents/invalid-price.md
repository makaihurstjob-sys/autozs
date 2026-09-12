# Invalid supplier prices and inherited evidence

Base: 4df30b8. Assigned worktree: C:/AutoZS/worktrees/invalid-price-20260911.

Reproduced 20 failing cases against the base: invalid zero/negative/nonfinite capture prices retained an earlier fresh observation, invalid shipping captures recorded observations, bulk imports overwrote captured fields while retaining old evidence, and the restoration gate admitted invalid numeric values or future observations.

Changes:
- Invalid capture prices clear price_observed_at; invalid shipping values clear shipping_observed_at. Zero shipping remains valid.
- Bulk URL import clears observation timestamps for overwritten price and shipping fields and its default stock=True assignment. Omitted price/shipping fields retain their previous evidence.
- Restoration requires a positive finite supplier price and finite nonnegative shipping, independently of stored timestamps, and rejects future observation timestamps. The existing inclusive 24-hour cutoff is preserved.

Isolation: tests/conftest.py sets DATABASE_URL=sqlite:///:memory: before imports, and test helpers create their own in-memory SQLite engines. No operational database, environment files, browser, service, or marketplace resources used.

Validation (DATABASE_URL=sqlite:///:memory:):
- Before fix: python -m pytest apps/api/tests/test_supplier_observations.py apps/api/tests/test_supplier_freshness.py -q --tb=no => 20 failed, 18 passed.
- After fix: same two files => 38 passed.
- python -m pytest apps/api/tests/test_supplier_observations.py apps/api/tests/test_supplier_freshness.py apps/api/tests/test_importer_duplicates.py apps/api/tests/test_ebay_revisions.py apps/api/tests/test_ebay_revision_fallback.py -q --disable-warnings => 116 passed.
- Final freshness rerun after preserving existing cutoff: 22 passed.

Limitations: invalid raw numeric values are retained as captured data but lose evidence and cannot authorize restoration. This does not tighten supplier browser detection heuristics or activate the code live. Publish/rotation eligibility is a separate assigned track.
