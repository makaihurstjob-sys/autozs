# Restock eligibility safeguards

Base: aeffcbc. Worktree: C:/AutoZS/worktrees/restock-guards-20260911.

Completed the resumed worker changes and independent review fixes. Generic recovery after an AUTOZS quantity-zero action now shares sold-listing eligibility: current affirmative supplier stock, available shipping and price, evidence within 24 hours, product/listing availability, and product exclusions. Queued ineligible restorations are cancelled. Quantity-zero reductions retain their existing path.

Eligibility is rechecked when leasing browser work, generating CSV, preparing/reusing a batch, and authorizing upload. A prepared sheet containing an ineligible or revoked restoration is cancelled; eligible running rows return to the queue for a fresh sheet, so the account can proceed on its next poll. Cancelled/paused restoration jobs cannot authorize cached upload, and terminal batches cannot return to uploading. Already-uploading outcomes remain unresolved for reconciliation rather than being requeued. External success remains recordable after supplier evidence changes.

## Validation

Fixtures inspected: tests/conftest.py uses sqlite:///:memory:, dependency overrides and StaticPool; revision tests create independent in-memory sessions. No operational env, databases, browser, services, or external supplier APIs used.

- Before the additional batch lifecycle fixes: from apps/api, `python -m pytest tests/test_ebay_revisions.py tests/test_ebay_orders.py -q`: 84 passed.
- Final revision implementation: from worktree root, `python -m pytest apps/api/tests/test_ebay_revisions.py -q`: 63 passed, including all four new batch lifecycle cases.
- `git diff --check`: passed. Existing datetime/pytest-asyncio deprecation warnings only.
- Independent reviewer /root/restock_review cleared the prepared/cancelled/uncertain-outcome lifecycle fixes after reinspection.

## Limits

Mocked/in-memory results do not establish live restocking. Browser fallback quantity handling is a separate existing concern under coordinator review; this task does not edit extension code. Upload authorization cannot retract an external action already in flight. A rejected prepared sheet returns an error on that poll, then the next poll can build a fresh batch. Existing batch membership lookup silently omits deleted job IDs; manual deletion/integrity hardening remains a separate follow-up.
