# eBay cancellation repair

Direct signed-in Seller Hub observations, account a.m.anim-59, September 26 2026 at 16:04:31 UTC:
- Order 04-15204-72108, local 7: This order was canceled. Refund initiated Sep 20.
- Order 22-15176-66586, local 8: This order was canceled. Refund initiated Sep 22.
- Sources: https://www.ebay.com/mesh/ord/details?mode=SH&orderid=04-15204-72108 and https://www.ebay.com/mesh/ord/details?mode=SH&orderid=22-15176-66586

Local API still showed imported orders, open fulfillment tasks and draft supplier orders. This disproves the earlier claim that unchanged imported rows established live, uncancelled orders. A successful report sync is not per-order cancellation evidence. The precise contents of the earlier downloaded report have not been recovered; do not claim the status-column defect definitively caused these two stale records.

Reproduced code gaps: only first populated status column was considered; cancellation could be overwritten by a later incomplete report; existing tasks were not blocked on cancellation; queued/placing approval returned before checking parent cancellation. Fixed those paths, cancel unpurchased drafts/queued work and revoke leases; retain supplier confirmations and purchased status, hold uncertain attempts for reconciliation. Preserve original cancellation evidence across incomplete syncs. Explicit negative cancellation labels are not cancellations. Agent instructions require direct, exact-order verification before recommending or approving purchase. Imported report records remain imports, not verified live eligibility.

Validation: targeted cancellation, eBay order import and fulfillment tests against in-memory SQLite. Operational record reconciliation must match exact account/order IDs and preserve original money and item records. This does not claim full unattended checkout readiness or a new automated live eBay verification gate.

Validation results: 53 targeted tests passed; after adding the new-order/autoflush regression and flush fix, all 15 cancellation regressions passed. No production DB was used in tests.
