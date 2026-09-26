# Purchase policy implementation checkpoint

Owner confirmed USD 500 per order, USD 100 daily, USD 0.25 minimum net profit.
The daily accounting timezone is America/Chicago, consistent with project scheduling.

Implemented:
- Exact-cent evaluation rejects unknown costs, unknown fees, inconsistent totals and insufficient profit.
- SQLite transaction serialization protects a shared persistent reservation ledger.
- Unique marketplace-order and supplier-draft keys prevent duplicate reservations.
- Reserved/submitting/uncertain amounts remain held across midnight and reconnects.
- Confirmed spend counts on the recorded Chicago day; existing manual purchases and unresolved legacy attempts count too.
- One-shot submission transition rejects repeat calls. Callers must commit it before any supplier action.
- Approval and checkout claiming reject orders already represented in the reservation ledger.

Not active: this worktree has not been integrated into the operational checkout.
No automatic purchase enabled, live purchase attempted, or runtime policy changed.

Remaining integration:
1. Add a disabled-by-default final-submission API requiring the current checkout token, fresh exact eBay evidence, final supplier totals, verified seller proceeds/fees and explicit other costs. Evaluate, reserve and begin submission in one transaction; return permission only after commit.
2. Wire final browser checkout to that one-shot API, preserving uncertainty if the response or supplier confirmation is lost. Do not retry a final click based on a timeout.
3. Connect confirmed purchase / uncertain outcomes to record_outcome. Confirmed actual amount must match the reservation; do not silently release holds on cancellation/failure.
4. Provide an evidence-based reconciliation path for failed/uncertain reservations; there is deliberately no automatic release or expiry.
5. Validate integrated behavior and activation separately. Model tables are additive and registered through domain.py; live schema creation has not occurred.

The ledger alone is not submission authorization. It trusts its internal caller's PurchaseEvaluation; the final API must construct that result from validated evidence and never accept a client-supplied profit figure.
