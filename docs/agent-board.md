# Agent assignment board

Coordinator: Benny. Setup date: September 11, 2026.
Round: initial parallel code audits completed and reviewed; no agents running and no live changes assigned.

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
