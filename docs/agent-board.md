# Agent assignment board

Coordinator: Benny. Setup date: September 11, 2026.
Round: initial parallel code audits; no live changes assigned.

| Task | Owner | Branch / worktree | Scope | Acceptance | Status |
| --- | --- | --- | --- | --- | --- |
| Posting audit | posting agent | agents/posting-20260911 / C:/AutoZS/worktrees/posting-20260911 | Read posting code; write docs/agents/posting-audit.md only | Identify next reproducible recovery gap with file evidence and validation plan | Prepared |
| Delivery audit | delivery agent | agents/delivery-20260911 / C:/AutoZS/worktrees/delivery-20260911 | Read delivery code; write docs/agents/delivery-audit.md only | Review safe activation prerequisites and next testable gap | Prepared |
| Inventory audit | inventory agent | agents/inventory-20260911 / C:/AutoZS/worktrees/inventory-20260911 | Read inventory/order code; write docs/agents/inventory-audit.md only | Trace sold-to-available lifecycle and report concrete gaps | Prepared |

All branches start from the coordination setup commit immediately following bbadfcb; record exact base when dispatching. Workers must not modify application code during this audit round. Coordinator owns all live resources; none are granted to workers.
