# Replacement publish numeric guard

Base: 4416b1d. Worktree: C:/AutoZS/worktrees/publish-numeric-20260912.

Sale replacement queueing now requires a positive finite supplier price and finite nonnegative shipping, independently of observation timestamps. Rotation candidates use the existing supplier eligibility helper before delivery/readiness/package work; that helper now enforces the same numeric rules. Its existing enqueue/start callers receive the same protection. Free shipping remains valid.

Baseline reproduction: the new targeted tests failed 9 cases and passed 9. Failures covered sale zero/negative/infinite price, infinite shipping, in-memory NaN, and rotation positive infinite price/shipping despite fresh observations. Persisted infinity values were committed and reloaded before exercising each flow. SQLite can coerce NaN to NULL (and shipping is NOT NULL), so NaN is checked in memory without flushing; both the sale gate and rotation's eligibility helper are covered.

Validation uses the existing client fixture's disposable in-memory SQLite databases. The checkout has no .env. Live browser, API, database, services, credentials and policies were not accessed. Rotation eligibility cases mock downstream readiness/package output to prove the queue gate independently; existing order and listing tests retain downstream coverage.

This is queue/eligibility validation, not proof of live publication or a universal final-submit freshness authorization. Supplier observation provenance and a queued job aging before final browser submission remain separate follow-ups.
