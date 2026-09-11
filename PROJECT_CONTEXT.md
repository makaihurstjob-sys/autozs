# AUTOZS shared project context

## Outcome

Automate the resale pipeline: source products, validate listing eligibility and delivery, post accurate listings, synchronize stock and price, and handle orders with minimal manual intervention. Measure unattended completion and intervention reasons; code completion percentages are estimates, not proof.

## Verified baseline: September 11, 2026

Operational checkout: C:/AutoZS/repo. Baseline commit: bbadfcb.
The scheduling persistence guard (541e6cf) is loaded in the operational extension. A real draft had an expired date; automatic correction and persistence through a live run remain unverified.
Delivery-worker API activation is verified. Broad delivery checks and the listing gate remain disabled pending a full live quote cycle. Home Depot returned errors on two products and the cart during the last checks; recheck before describing that as a current outage.
See docs/delivery-quote-tracking.md for test and activation evidence. Earlier handoffs and queue counts are historical; confirm current state before acting.

## Parallel tracks

- Posting reliability: schedule persistence, descriptions, item specifics, review recovery.
- Supplier/delivery: isolated cart lifecycle, quote evidence, listing eligibility.
- Inventory/orders: sold-item availability, supplier stock, fulfillment handoffs.
- Benny/coordinator: assignment, review, integration, live resource ownership, progress reporting.

Read docs/agent-coordination.md for the working protocol. The coordinator owns updates to this context; workers return findings rather than concurrently editing it.
