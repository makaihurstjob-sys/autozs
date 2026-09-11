# Account-scoped sold listing replacement

Date: 2026-09-11. Base: `8355c1b`. Branch: `agents/inventory-fix-20260911`.

## Change

Replacement reconciliation now retains distinct `(product_id, account_id)` pairs from non-cancelled orders and restricts each zero-quantity listing lookup to that sale account. A newer ended item belonging to another seller can no longer redirect or suppress the selling account's repair. Each sold account is considered once per pass, retaining account-specific active/scheduled listing and open publish-job guards. Stock revision enqueueing continues to receive distinct product IDs.

## Evidence

Six new parameterized regressions were run with the service file temporarily restored from `8355c1b`, then restored to the edited version in a `finally` block. All six failed on the baseline. The direct counterexample queued `other-seller` even though only `a.m.anim-59` had a sale.

Coverage includes a sale with only another account's eligible ended listing; newer other-account listing alongside the selling account's ended listing; two selling accounts; repeated sales on one account; a third account with only a cancelled order; active/scheduled listings or an open job suppressing only their own account; and repeated reconciliation without duplicate jobs.

Tests use SQLite in-memory fixtures. The worktree has no `.env`; application background report, source refresh, traffic and push loops are disabled for memory databases. No operational database, API, browser, service or credentials were used.

## Validation

Command: `C:/AutoZS/venv/Scripts/python.exe -m pytest apps/api/tests/test_ebay_orders.py apps/api/tests/test_ebay_revisions.py -q --disable-warnings` from the assigned worktree. Result: **59 passed** in 41.22 seconds (existing deprecation warnings). `git diff --check` passed.

## Limits and follow-up

This is local regression evidence, not live restock validation. Existing supplier freshness and exclusion guards remain in place for replacement creation. The separate generic stock-recovery freshness/exclusion concern in `inventory-audit.md` is outside this assignment. Idempotency is verified across sequential reconciliation passes, not concurrent independent database transactions.

