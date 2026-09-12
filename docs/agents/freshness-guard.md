# Freshness guard for stock_restoration_block

Implementation follow-up to `docs/agents/supplier-freshness-followup.md`, based at commit
2042583 on branch `agents/freshness-guard-20260911`. Scope: make positive stock
restoration require genuine, fresh, explicit per-field evidence instead of trusting
`SupplierProduct.updated_at`, which bumps on any metadata edit and is not proof any of
stock/price/shipping was actually re-observed.

## Behavior implemented

`apps/api/app/services/ebay_revisions.py`:

- `RESTOCK_EVIDENCE_FRESHNESS = timedelta(hours=24)` (module constant, ~line 47).
- New helper `_stale_observation_reason(label, observed_at, now)` (~line 210): returns
  `None` only if `observed_at` is non-null and `now - observed_at < 24h`; otherwise
  returns a reason string. A `None` timestamp and a stale timestamp are treated
  identically -- both fail.
- `stock_restoration_block` (~line 222): after the existing checks it preserved
  unchanged (listing/product/exclusion eligibility, `supplier.in_stock is True`,
  `supplier_availability_block`, `supplier.last_price is not None`), it now requires
  **all three** of `supplier.stock_observed_at`, `supplier.price_observed_at`,
  `supplier.shipping_observed_at` to independently pass `_stale_observation_reason`.
  The old `supplier.updated_at < now - 24h` check is removed entirely -- there is no
  fallback to `updated_at` for rows that lack the new columns. A legacy/migrated row
  with all three timestamps NULL fails this check unconditionally, even if
  `updated_at` was touched a second ago.
- No other function in the file was changed. `supplier_availability_block` (the
  quantity-zero / "mark out of stock" path) is untouched and still requires no
  observation timestamps, so reductions remain unaffected by missing evidence.
  `update_ebay_revision_job` (recording a completed/authoritative action) never calls
  `stock_restoration_block`, so previously-approved jobs still apply cleanly even if
  evidence goes stale in the interim.

## Shim added (temporary -- coordinator must reconcile)

`apps/api/app/models/domain.py`, `SupplierProduct` class (~line 216): added three
nullable `DATETIME` columns with **no default and no `onupdate`**:

```python
stock_observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
price_observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
shipping_observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

This duplicates the schema the parallel `observations-20260911` worktree is adding
(same three field names/types, per the background doc). It exists **only** so this
worktree's tests could exercise real explicit-observation evidence without depending on
that worker's unmerged model/importer/migration changes. It does **not** include:
- the additive startup migration entry in `apps/api/app/main.py` (out of scope --
  explicitly not attempted here),
- any importer/capture logic that actually populates these fields from real captures.

**When merging with the observations worktree: drop this duplicate column definition
from `domain.py` and take theirs (or vice versa -- they should be byte-identical
columns), then confirm `stock_restoration_block` still compiles against whichever
final column definitions land.** If their migration/importer changes land as expected,
no further change to `ebay_revisions.py` should be needed -- this guard only reads the
three attributes, it doesn't care how they get populated.

## Test results

Ran with a disposable in-memory SQLite engine (`create_engine("sqlite:///:memory:")`,
`Base.metadata.create_all`), no live DB/browser/credentials touched.

```
pytest tests/test_ebay_revisions.py tests/test_ebay_orders.py tests/test_supplier_freshness.py
99 passed
```

Full suite:
```
pytest
397 passed, 1 failed (pre-existing, unrelated)
```

The one failure, `tests/test_ebay_report_files.py::test_automatic_active_listings_report_imports_real_ebay_csv_and_preserves_scheduled`,
is a PDT-to-UTC timezone-offset assertion (`23:00:01` expected vs `19:00:01` actual --
a 4-hour, not 7/8-hour PDT offset, i.e. environment/DST-table dependent). Verified by
stashing this branch's changes and re-running against the unmodified base commit
2042583: it fails identically there. Not touched, not in scope.

## Fixtures updated to keep existing coverage passing

Per the freshness change, several existing fixtures previously relied on
`supplier.updated_at` being recent to represent "fresh supplier evidence" for a
restock. Since `updated_at` is no longer consulted by `stock_restoration_block`, these
were updated to also set the three new observation timestamps (fresh by default,
staled where the test intends to simulate expired evidence):

- `apps/api/tests/test_ebay_revisions.py`: `_sourced_product()` now stamps all three
  observed_at fields fresh by default; `_invalidate_restock()`'s `"stale"` branch now
  stales the three observed_at fields (previously staled `updated_at`); two tests that
  directly staled `supplier.updated_at` to simulate an expired restock
  (`test_invalid_restock_does_not_block_zero_quantity_batch`,
  `test_invalid_prepared_restock_releases_safe_rows_for_next_batch`) now stale the
  three observed_at fields instead.
- `apps/api/tests/test_ebay_orders.py`: the three tests that exercise
  `reconcile_sold_listing_replacements` -> `enqueue_ebay_stock_revisions` ->
  `stock_restoration_block` for an active, quantity-zero listing
  (`test_sold_active_listing_restores_same_item_and_never_publishes`,
  `test_sold_stock_restoration_requires_fresh_stock_and_no_duplicate`,
  `test_multiple_sold_out_items_queue_only_one_restore`) now also stamp the three
  observed_at fields; the `stale` parametrized case in the second test now stales the
  observed_at fields rather than `updated_at`. Tests that route through
  `_queue_replacement_publish` (the "ended listing" replacement-publish path, a
  separate, out-of-scope function in `app/services/orders.py` that still checks
  `updated_at` directly) were left untouched -- that function does not call
  `stock_restoration_block` and was not part of this task's scope.
- `apps/api/tests/test_ebay_revision_fallback.py`: the shared `db` fixture's
  `SupplierProduct` now also stamps the three observed_at fields fresh, so the
  `[queued-restore_stock]` parametrization of
  `test_fallback_skips_unsupported_actions_without_mutating_them` (which asserts a
  *legitimately eligible* queued restock job is left untouched by
  `cancel_ineligible_queued_restocks`) continues to pass -- without this, the newly
  strict freshness check would cancel that job for lacking evidence, which was not
  what that test was probing.

## New test file

`apps/api/tests/test_supplier_freshness.py` -- 11 tests, isolated from the existing
suite, using only a disposable in-memory SQLite session. Covers: all-three-fresh
allows restoration; each of the three timestamps missing (individually) blocks; each
of the three timestamps stale (individually, >24h, with the other two fresh) blocks;
a boundary case just past 24h; a "legacy row" (all three NULL, `updated_at` recent)
is blocked, not grandfathered; the quantity-zero/`supplier_availability_block` path is
unaffected by missing observation timestamps; and recording an already-approved,
already-running completed restock job via `update_ebay_revision_job` is unaffected by
evidence expiring afterward.

## Open questions / what the coordinator needs to reconcile at integration

1. **Column duplication**: `domain.py` will have two independent additions of the same
   three column names once both worktrees merge. Needs a straightforward de-dup (keep
   one definition), not a design decision.
2. **Startup migration**: `apps/api/app/main.py`'s additive migration list (~line 121,
   `"supplier_products": {...}`) does not yet include these three columns. Someone
   (per the background doc, this was intentionally left to whichever worker owns
   importer/migration work) needs to add them there for real deployments; disposable
   SQLite tests don't need it since they call `Base.metadata.create_all` directly.
3. **Population**: nothing in this worktree writes to `stock_observed_at` /
   `price_observed_at` / `shipping_observed_at`. Until the observations worker's
   importer changes land and are wired to real Home Depot/Amazon captures, every
   `SupplierProduct` row will have all three NULL, and **every** restock will be
   blocked in practice by this guard (by design, per the background doc's "expect
   pending restorations to be held/cancelled until refresh succeeds" note). That's the
   intended fail-safe behavior, but the coordinator should sequence rollout so the
   importer change lands close to (ideally before, or atomically with) this guard
   change reaching a live environment, or restocks will visibly stall.
4. No changes were made to `app/services/orders.py`'s `_queue_replacement_publish`,
   which has its own, separate, still-`updated_at`-based freshness check for the
   "ended listing needs republishing" path. That function was out of scope for this
   task (not `stock_restoration_block` or a helper it calls), but it has the same
   underlying weakness this task fixed for `stock_restoration_block`. Flagging it as a
   likely next-round candidate, not fixing it here.
