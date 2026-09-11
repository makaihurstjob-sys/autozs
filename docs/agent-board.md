# Agent assignment board

Coordinator: Benny. Setup date: September 11, 2026.
Round: implementation round resumed from 8355c1b on September 11, 2026; live resources remain coordinator-only. Previous session agents were absent; three replacement agents inspected and resumed their existing assigned worktrees without discarding edits.

## Active implementation round

| Task | Owner | Branch / worktree | Permitted edits | Acceptance | Status |
| --- | --- | --- | --- | --- | --- |
| Uncertain submission guard | /root/posting_fix | agents/posting-fix-20260911 / C:/AutoZS/worktrees/posting-fix-20260911 | tools/chrome-extension posting code and tests; docs/agents/posting-implementation.md | Persist before click, hold unknown outcomes across restart, reconcile confirmation, isolated regressions | Resumed for completion/review in current session |
| Bounded delivery trial | /root/delivery_trial | agents/delivery-trial-20260911 / C:/AutoZS/worktrees/delivery-trial-20260911 | delivery API/service/tests; tools/delivery-check-extension if needed; docs/agents/delivery-implementation.md | One product/ZIP with broad gate off, revocation and existing behavior covered | Resumed for completion/review in current session |
| Account-scoped replacement | /root/inventory_fix | agents/inventory-fix-20260911 / C:/AutoZS/worktrees/inventory-fix-20260911 | apps/api/app/services/orders.py and tests/test_ebay_orders.py; docs/agents/inventory-implementation.md | Reproduce cross-account bug, fix account-scoped repair and idempotency | Resumed for completion/review in current session |

Base for all three: 8355c1b. No operational API/database/browser actions or service activation authorized to workers. Inspect test fixtures before execution; use only disposable databases/mocked external services. Report scope expansion needs to coordinator. Earlier audit-round restrictions below are historical to that round.

| Task | Owner | Branch / worktree | Scope | Acceptance | Status |
| --- | --- | --- | --- | --- | --- |
| Posting audit | posting agent | agents/posting-20260911 / C:/AutoZS/worktrees/posting-20260911 | Read posting code; write docs/agents/posting-audit.md only | Identify next reproducible recovery gap with file evidence and validation plan | Reviewed and integrated; source 0e8d49b |
| Delivery audit | delivery agent | agents/delivery-20260911 / C:/AutoZS/worktrees/delivery-20260911 | Read delivery code; write docs/agents/delivery-audit.md only | Review safe activation prerequisites and next testable gap | Reviewed and integrated; source 7071f4b |
| Inventory audit | inventory agent | agents/inventory-20260911 / C:/AutoZS/worktrees/inventory-20260911 | Read inventory/order code; write docs/agents/inventory-audit.md only | Trace sold-to-available lifecycle and report concrete gaps | Reviewed and integrated; source 9d20917 |

All branches start from 23fcd18. Session owners: /root/posting, /root/delivery, /root/inventory. Workers must not modify application code during this audit round. Coordinator owns all live resources; none are granted to workers.

## Next implementation assignments (queued, not dispatched)

- Posting: persist and reconcile an uncertain final submission before permitting retry. Mock reproduction confirms misleading draft/retry classification, not a real duplicate listing.
- Delivery: add a single-product/ZIP trial scope independent of broad coverage; enforce revocation and lease scope.
- Inventory: retain account identity during ended-item replacement reconciliation; reproduce cross-account selection in isolated tests before fixing. Separately review generic stock recovery freshness/exclusion guards.

## Round validation

All three workers completed independently in distinct branches, committed only their assigned reports, and handed off for serial review/cherry-pick. Coordinator verified branch paths, shared instruction files, absence of runtime .env/dev.db, and clean whitespace checks. Existing tracked SQLite sidecars remain unchanged by this work; the operational checkout's pre-existing dev.db-shm modification was not staged.
Delivery worker: ten mocked tests passed. Posting: schedule persistence tests and one isolated uncertain-submission reproduction passed. Inventory: static audit only. Application behavior and live readiness have not changed in this setup round.

## Current session continuation
Posting owner /root/posting_fix resumes unfinished guard in its existing worktree, base 8355c1b. Delivery owner /root/delivery_review reviews its completed 6451015 worktree and activation readiness; report-only scope docs/agents/delivery-implementation.md. Inventory owner /root/inventory_review reviews completed c9520e5 and verifies replacement compatibility; report-only scope docs/agents/inventory-implementation.md. Coordinator reviews combined integration checkout aeffcbc and integrates serially. All workers remain prohibited from live resources.


Follow-up assigned to /root/inventory_review: agents/restock-guards-20260911 at C:/AutoZS/worktrees/restock-guards-20260911, base aeffcbc. Scope apps/api/app/services/ebay_revisions.py, apps/api/tests/test_ebay_revisions.py, docs/agents/restock-guards.md. Reproduce and fix generic out-of-stock RESTOCK bypass of freshness/exclusion/affirmative stock checks while preserving valid recovery. Disposable tests only; no live resources. Status assigned.
Restock scope expanded: minimal shared eligibility call sites in apps/api/app/services/ebay_revision_batches.py and ebay_revision_csv.py plus corresponding tests, to enforce queued execution checks. No live resource grant.
