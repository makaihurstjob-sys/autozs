# Independent restock review — September 11, 2026

Reviewer base: 7885760, checkout C:/AutoZS/worktrees/restock-review-20260911.
Reviewed the uncommitted revision-services/tests diff in C:/AutoZS/worktrees/restock-guards-20260911 read-only. No operational resources or databases accessed. This is static review, not a claim of independent test execution or live validation.

## Findings sent to coordinator and implementation owner

1. Prepared batch starvation (resolution pending): `prepare_next_ebay_revision_batch` invokes `_assert_batch_restock_eligible` for the oldest active prepared batch. A failed check raises without removing that batch from active status. `/ebay/revision-batches/next` converts it to HTTP 409, leaving every subsequent poll blocked, including unrelated quantity-zero jobs. An already-open uploader can catch its own PATCH failure and mark needs_review, but a failure at /next never reaches that cleanup. Persist a review/cancellation transition for a definitely unsubmitted prepared batch and allow subsequent safe work. Preserve uploading/waiting-results uncertainty.

2. Cached CSV authorization ignores job cancellation (resolution pending): `_assert_batch_restock_eligible` only calls `restock_job_block`; it does not reject a cancelled/paused constituent job, missing constituent, or a terminal batch. Cancel a prepared restock job, refresh supplier evidence, then PATCH uploading: eligibility alone passes for the cached CSV. Require a valid prepared-batch/member lifecycle before authorizing upload. Tests should cover cancellation followed by evidence becoming valid again.

3. Browser fallback cannot execute stock actions (pre-existing, follow-up assigned by coordinator): `start_next_ebay_revision_job` selects every action except end_zero_view. `tools/chrome-extension/ebay-fill.js:1004` (`runPriceRevisionWorkflow`) fills price/title; it does not dispatch stock actions or set quantity. Completion then makes the backend quantity appear restored/reduced without the quantity change. Keep stock actions in bulk execution or implement explicit quantity execution; restrict unsupported fallback claims.

## Guard assessment

The shared restoration predicate now checks listing/product availability, relist blocking, product exclusions, affirmative supplier stock, shipping availability, price presence and a 24-hour row timestamp. It is applied at stock queue creation, CSV generation, queued-job cancellation, and immediately before bulk uploading. Quantity-zero reductions bypass the restoration predicate. Recording confirmed completion remains possible after evidence changes, which correctly preserves external facts.

The uploader awaits a successful PATCH to uploading before `upload.click()` (`tools/chrome-extension/ebay-revision-upload.js:300`), so backend rejection prevents that click. A supplier change after successful authorization remains a short unavoidable check/use interval in this design.

An ineligible running browser job currently returns None without resolving status. For normal jobs this is a conservative hold bounded by the 15-minute lease: `release_expired_ebay_revision_jobs` requeues/exhausts it, after which cancellation applies. A malformed running job with no lease would stall indefinitely. Do not automatically retry uncertain external work solely to remove this hold.

Freshness is row recency, not proof of a fresh affirmative stock observation: `importer.py:765-785` retains absent capture stock/price fields but unconditionally refreshes supplier.updated_at; the capture path at 664-681 does likewise. This predates this change and also affects sold-restock eligibility. A separate supplier evidence timestamp/complete-observation follow-up is warranted before describing the guard as strict fresh stock verification.

## Handoff

No application changes made. Two batch lifecycle defects were sent to /root/restock_finish for regression-backed repair. Final clearance depends on reviewing that resulting diff and combined isolated tests. Canonical board read at start and handoff; no worker live-resource grant.

## Follow-up review of worker lifecycle repair

Re-read the updated worker batch service after the initial report. The helper now persistently cancels an invalid prepared batch, cancels ineligible running restoration rows, and requeues eligible running rows for a fresh sheet; a subsequent poll can proceed after the initial 409. It rejects non-running restoration members and uploading from terminal batch states. Uploading/waiting-results batches are not automatically requeued. These changes address findings 1 and 2 for existing members; clearance is static pending the worker and coordinator test results.

Residual integrity follow-up: `_batch_jobs` silently omits nonexistent IDs from job_ids_json. A manually deleted member therefore cannot be revalidated against cached CSV. No normal member-deletion path was established in this review, so this is not a demonstrated normal-workflow blocker.
