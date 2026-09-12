# Order cancellation and initial ZIP filter — September 11, 2026

- User authorized cancelling latest mulch sale, sending the same 20% apology offer, and starting availability filtering with buyer ZIP.
- Order 20-15136-17831 (local order/supplier task 6): eBay cancellation 5453208051 accepted for Out of stock or damaged. Cancellation page confirmed refund initiated, processing pending. Order details showed $8.08 cancelled including $0.55 tax.
- Supplier task 6 PATCH returned cancelled; no supplier purchase.
- Buyer 310jeff: sent apology explaining delivery unavailable, full refund initiated, 20% off another item, contact before purchasing to confirm availability and arrange discount. eBay Message sent confirmation, rendered outgoing message, empty composer verified. No second send.
- eBay listing 800627028434 still had one unit; ended using Seller Hub single-item action. Item page confirmed ENDED. Local listing 244 tombstoned with delivery_unavailable reason and relist_blocked=true, API 200 verified.
- Live delivery policy PUT/GET verified enabled=true, postal_codes=[84532]. Dedicated isolated worker at port 9335 was idle before activation, separate from checkout port 9224 and operations port 9225.
- Five ZIP jobs enrolled. First needs_review after one attempt: Missing delivery page evidence. Four queued. No successful quote cycle claimed. Gate holds missing/failed evidence; this is new Home Depot listing coverage, not a completed audit of all live listings or nationwide availability.
- Agent handoff 2c24fe8 integrated into integration checkout as 4f3eafd; 21 isolated delivery tests passed. Existing-listing audit needs explicit enrollment and typed regional unavailability before automatic withdrawal/restoration. See integration docs/agents/zip-filter.md.
- Prior traffic alert edits and supplier-freshness integration were preserved; no Master Dashboard deployment touched or API restart performed.
