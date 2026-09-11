# Inventory lifecycle audit

Date: 2026-09-11. Base: `23fcd18`. Worker branch: `agents/inventory-20260911`.
Scope: static code and existing-test review only; no live resources, application edits, or test execution.

## Current lifecycle

- New, non-cancelled order import matches a product and decrements the exact account/item listing quantity (`apps/api/app/services/orders.py:179-191`, `256-295`). An unmatched item number does not fall back to another listing.
- Active zero-quantity items retain their existing item ID. Reconciliation invokes stock revision scheduling (`orders.py:305-315`); the sold restore guard requires fresh supplier stock, no competing positive-quantity listing, no open publish job, newest eligible zero-quantity item, and an account-matched sale (`apps/api/app/services/ebay_revisions.py:305-343`).
- Ended items use a replacement publish job. Fresh supplier evidence, exclusions, other sellable listings and existing publish jobs gate creation (`orders.py:399-452`). Worker maintenance calls reconciliation (`apps/api/app/main.py:215`).
- Existing tests cover import idempotency, exact-item matching, active-item restoration, stale stock, exclusions, competing listings, other-account rejection for active items, and duplicate restore suppression (`apps/api/tests/test_ebay_orders.py:177-306`). These are implementation coverage, not evidence that the operational browser completed restocking.

## Highest-value gap: ended replacement reconciliation loses account scope

`orders.py:308-313` reduces non-cancelled sales to product IDs. Its candidate query at `321-333` selects the newest zero-quantity listing for that product across all accounts. It then takes the selected listing's account (`337`) and can queue a publish for it (`365-371`). `_queue_replacement_publish` has no sale/account check (`399-452`).

Concrete reproducer: product P has a non-cancelled sale only on account A, plus a newer ended zero-quantity listing on account B. With fresh supplier evidence and no competing B listing/job, reconciliation chooses B and queues B's replacement without a B sale. If A also has an ended item awaiting repair, selecting only B can leave A unrepaired. The active restore path explicitly checks sale account at `ebay_revisions.py:339-342`; the ended path lacks that equivalent.

Proposed next change: reconcile distinct `(product_id, account_id)` sale pairs and restrict candidate listings to the pair's account. Preserve existing exclusions and duplicate suppression. Avoid changing live quantities until isolated regressions pass.

Validation plan: extend the in-memory order tests with (1) sale on A and ended listing only on B -> no publish; (2) ended listings and sales on both A and B -> one appropriate job per account; (3) a second pass -> no duplicates; (4) a sellable or open-job sibling on A -> only A suppressed. Run the focused order tests and stock-revision tests after inspecting their fixture/runtime configuration.

## Separate follow-up: generic stock recovery bypasses the sold-restore guard

`ebay_revisions.py:258` allows `already_out_of_stock` to short-circuit `sold_listing_restock_allowed`. The generic supplier blocker (`173-189`) does not require affirmative `in_stock=True`, a fresh timestamp, or product exclusions. Thus a prior completed out-of-stock revision plus old/unknown stock evidence with non-negative shipping can queue restoration; a paused product is also not excluded by the outer query (`230`). This is a distinct safety-policy gap to investigate before broad unattended restoration, not a verified live incident.

Validation plan: fixture a completed out-of-stock revision, then stale/unknown supplier stock or a paused product; assert restoration remains held. Confirm intended recovery policy before changing this shared path, and retain permitted out-of-stock reductions.

## Limitations

No tests run and no operational state checked. Findings are code-path evidence at the stated base; no claim about current affected listings or account usage. Tests' `conftest.py` uses an in-memory database override, but application lifespan/settings also need review before any execution. No credentials or operational database read.
