# Purchasing readiness — 2026-09-10

Automatic purchasing is not yet enabled end to end. The Home Depot checkout worker verifies checkout and stops for owner review before Place order.

## Verified findings

- New eBay order imports create fulfillment tasks, but do not automatically call supplier-order preparation.
- Preparing an existing purchased order previously refreshed its readiness and could reset it to draft. Delivered orders were absent from the active-order lookup and could produce a second supplier order.
- Reapproving a purchased or active order previously reset it to queued and cleared its checkout token.
- Expired checkout leases previously returned to the queue without checking whether a purchase had happened.
- The three recent live purchases are now marked shipped. None is a valid new purchase test.

## Changes

Preserve recorded purchases when preparing again; reject purchase-state regression and reapproval; preserve queued/running checkout on repeated preparation or approval; hold expired or already fulfilled checkout candidates for reconciliation.

## Remaining work before unattended purchasing

1. Automatically prepare eligible new sales without approving or charging them.
2. Validate cart item identity and quantity independently of matching subtotal (the existing cart check is primarily subtotal-based).
3. Exercise the full checkout against a new eligible sale and verify destination-specific delivery and final total.
4. Implement a durable submission-attempt record and supplier confirmation reconciliation before enabling the final purchase click. Session-local checks alone cannot make an uncertain payment retry safe.

These changes do not enable the final purchase click or purchase any item.
