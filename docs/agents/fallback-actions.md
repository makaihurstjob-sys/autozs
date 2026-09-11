# Browser fallback action compatibility

Base: `9e96c49`. Worktree: `C:/AutoZS/worktrees/fallback-actions-20260911`.

The browser fallback edits prices only. `start_next_ebay_revision_job` previously excluded only `end_zero_view`, allowing quantity actions and unknown future actions to be offered as price work. Both queued selection and running-job recovery now require `revise_price`, the model's actual default action.

The restriction does not cancel or complete unsupported jobs. Valid queued stock actions remain queued for bulk processing; active unsupported leases are not reoffered. Existing expiration handling remains unchanged, including normal requeue/failure on exhausted expired leases. This change does not recover outcomes of previously executed unsupported actions.

Thirteen isolated regression cases cover queued/running out-of-stock, restore, both retirement actions, legacy end, and unknown action preservation, price dispatch behind unsupported work, and running price recovery before queued price work. Fixtures include an eligible active listing and fresh affirmative supplier evidence so integration with the separate restock eligibility guard tests action compatibility, not deliberately invalid stock evidence. Settings/account eligibility are mocked, and all database sessions are SQLite memory databases. No operational resources or environment files were accessed.

Before the selector fix: **10 failed, 3 passed**. Reproduced again with final eligible fixtures by temporarily restoring the two baseline selectors and restoring fixed bytes in `finally`.

After the fix, command `C:/AutoZS/venv/Scripts/python.exe -m pytest apps/api/tests/test_ebay_revision_fallback.py apps/api/tests/test_ebay_revisions.py -q --disable-warnings`: **47 passed** (existing deprecation warnings). `git diff --check` passed. Tests are isolated regression evidence, not live marketplace validation.

Coordinator must integrate serially with the restock branch, preserving its cancellation guard and these two positive action selectors, then include the new test file in the combined backend run.
