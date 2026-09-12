# AUTOZS shared project context

## Outcome

Automate the resale pipeline: source products, validate listing eligibility and delivery, post accurate listings, synchronize stock and price, and handle orders with minimal manual intervention. Measure unattended completion and intervention reasons; code completion percentages are estimates, not proof.

## Verified baseline: September 11, 2026

Operational checkout: C:/AutoZS/repo. Baseline commit: bbadfcb.
The scheduling persistence guard (541e6cf) is loaded in the operational extension. A real draft had an expired date; automatic correction and persistence through a live run remain unverified.
Delivery-worker API activation is verified. Broad delivery checks and the listing gate remain disabled pending a full live quote cycle. Home Depot returned errors on two products and the cart during the last checks; recheck before describing that as a current outage.
See docs/delivery-quote-tracking.md for test and activation evidence. Earlier handoffs and queue counts are historical; confirm current state before acting.

## Integration checkpoint: September 11 continuation

The isolated integration checkout is C:/AutoZS/worktrees/integration-20260911. Application checkpoint 1984810 includes account-scoped replacements, one-supplier/ZIP delivery trials, durable local uncertain-submission guards, restock eligibility checks through bulk-upload authorization, prepared-batch recovery, and browser fallback restricted to price actions. These application changes have not been promoted to C:/AutoZS/repo or activated live. See docs/agents/activation-review.md for current activation prerequisites and docs/agent-board.md in the operational checkout for canonical assignments and final validation results.

Supplier freshness still uses a generic row timestamp, which may advance without fresh stock/price observations. The next implementation is specified in docs/agents/supplier-freshness-followup.md. Mocked tests do not prove live marketplace outcomes or current supplier availability.

## Parallel tracks

- Posting reliability: schedule persistence, descriptions, item specifics, review recovery.
- Supplier/delivery: isolated cart lifecycle, quote evidence, listing eligibility.
- Inventory/orders: sold-item availability, supplier stock, fulfillment handoffs.
- Benny/coordinator: assignment, review, integration, live resource ownership, progress reporting.

Read docs/agent-coordination.md for the working protocol. The coordinator owns updates to this context; workers return findings rather than concurrently editing it.
