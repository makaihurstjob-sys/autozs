# Supplier observation timestamps -- implementation report

Implements the fix proposed in `docs/agents/supplier-freshness-followup.md`.
`SupplierProduct` now records *when* stock, price and shipping were each
actually observed from the supplier, instead of relying on the generic
`updated_at` (which a title-only or price-only capture also bumps).

## What changed

### `apps/api/app/models/domain.py` (`SupplierProduct`, ~line 202)
Added three nullable columns, no default, no ORM `onupdate`:
- `stock_observed_at: datetime | None`
- `price_observed_at: datetime | None`
- `shipping_observed_at: datetime | None`

### `apps/api/app/main.py` (`_ensure_lightweight_columns`, ~line 121)
Added the same three columns (`DATETIME`, nullable) to the existing additive
`supplier_products` migration entry. Uses the same idempotent
"add column if not already present" loop as every other table in this
function -- no backfill statement was added for these three columns, and
nothing stamps them at migration time, so legacy rows come out of migration
with the columns present but `NULL`.

### `apps/api/app/services/importer.py`
Two new helpers, placed next to `_log_supplier_snapshot` (~line 1002, now
just above it):
- `_reset_observations_on_source_change(supplier, new_source_url)` -- clears
  all three observation timestamps when `supplier.source_url` is about to
  change to a different value. Evidence from the old source URL/listing must
  not be attributed to the new one.
- `_apply_supplier_capture(supplier, *, source_price, source_shipping,
  source_in_stock, source_price_unavailable, received_at)` -- the single
  place that both decides the effective field values (unchanged prior
  behavior) *and* decides whether this capture counts as an observation of
  that specific field. Rules, matching the follow-up doc:
  - `stock_observed_at` <- `received_at` iff `source_in_stock is not None`
    (i.e. explicitly `True` or `False`).
  - `price_observed_at` <- `received_at` iff a finite, positive `source_price`
    was supplied, OR `source_price_unavailable is True`. A `False`/absent
    price-unavailable flag alone is not evidence and does not stamp anything.
  - `shipping_observed_at` <- `received_at` iff `source_shipping is not None`.
    If `source_in_stock is False`, shipping is invalidated immediately
    (`last_shipping = -1.0`) **and** `shipping_observed_at` is cleared to
    `None` -- an out-of-stock capture is never treated as affirmative
    shipping evidence, even if a shipping value happened to be supplied in
    the same capture (out-of-stock invalidation runs after and wins).

`received_at` is computed once per capture (`datetime.utcnow()`) and shared
across all three fields touched by that call, so a single complete capture
stamps stock/price/shipping to the exact same instant -- there is one server
receipt time per capture event, not three independently-drifting clocks.

Call sites updated:
- `import_captured_product` (~line 616): creates/finds the `SupplierProduct`,
  calls `_reset_observations_on_source_change` before overwriting
  `source_url`, then calls `_apply_supplier_capture`. `supplier.updated_at` is
  now set from the same `received_at` value.
- `update_product_from_capture` (~line 737): same `_apply_supplier_capture`
  call; this path never changes `source_url`, so no identity-reset call is
  needed here.
- Bulk/URL importer path inside `import_products` (~line 532-548): calls
  `_reset_observations_on_source_change` (bulk import can still re-point an
  existing product's supplier row at a new source URL) but **never** calls
  `_apply_supplier_capture` and never stamps any of the three timestamps --
  its `supplier.in_stock = True` is a default, not an observation, per the
  explicit requirement.
- `_log_supplier_snapshot` (~line 1002, now renumbered slightly lower):
  reviewed, left unchanged. It only writes a `PriceSnapshot` audit row from
  already-effective values; it doesn't touch `SupplierProduct` fields, so it
  has no observation timestamps to set.

Added `import math` (used for `math.isfinite` in the price check).

## Tests -- `apps/api/tests/test_supplier_observations.py`

Note: the task scope said `tests/test_supplier_observations.py`; this repo
keeps all API tests under `apps/api/tests/` (see `test_importer_duplicates.py`
etc. -- there is no top-level `tests/` directory), so the file was placed
there to match convention and actually be collected by the existing test
setup (`apps/api/tests/conftest.py` sets `DATABASE_URL` and `sys.path`).

Six tests, all passing:
1. `test_title_only_and_single_field_captures_do_not_cross_refresh_other_fields`
   -- title-only, then price-only, then shipping-only captures each move only
   their own timestamp.
2. `test_complete_explicit_capture_sets_all_three_observed_timestamps_to_now`
   -- a full explicit capture sets all three to the identical shared
   `received_at`.
3. `test_negative_stock_and_unavailable_price_recorded_immediately_not_resurrected_by_incomplete_capture`
   -- out-of-stock + price-unavailable stamps immediately and clears
   shipping; a later title-only capture cannot move those timestamps forward
   or flip the recorded state back.
4. `test_source_identity_change_clears_observations_but_unrelated_edit_does_not`
   -- an unrelated title edit on the same source leaves all three timestamps
   untouched; capturing the same physical Home Depot product (same trailing
   product id / stable supplier SKU) from a new listing URL clears all three.
5. `test_bulk_url_import_never_stamps_observation_timestamps` -- extra
   coverage beyond the required five, confirming the bulk/URL import default
   path never sets any of the three fields.
6. `test_migration_adds_columns_leaves_existing_rows_null_and_is_idempotent`
   -- builds a raw pre-migration `supplier_products` table (matching the real
   schema minus the three new columns) with one legacy row, monkeypatches
   `app.main.engine` to point at it, runs `_ensure_lightweight_columns()`
   twice, and asserts the columns exist, the legacy row's new columns stay
   `NULL` both times, and the second run doesn't error.

## Test results

Runs performed against disposable in-memory SQLite engines (no live database,
no network access):
- `python -m pytest apps/api/tests/test_supplier_observations.py -v` -- 6 passed.
- `python -m pytest apps/api/tests/test_importer_duplicates.py apps/api/tests/test_supplier_receipts.py apps/api/tests/test_delivery_quotes.py -v` -- 9 passed (existing importer/supplier-adjacent tests, confirming no regression).
- `python -m pytest apps/api/tests/ -q` (full suite) -- run for broader regression coverage; final pass/fail count recorded in the commit that lands this doc.

The only warnings seen anywhere were pre-existing `DeprecationWarning`s for
`datetime.utcnow()`, used throughout the codebase already (not introduced by
this change) -- not test failures.

## Exact names for downstream consumers (freshness-guard / integration)

On `SupplierProduct` (`app/models/domain.py`):
- `stock_observed_at: datetime | None`
- `price_observed_at: datetime | None`
- `shipping_observed_at: datetime | None`

Semantics: each is `None` until a capture supplies *explicit* evidence for
that specific field (per rules above). `None` must be read as "never
observed" / "not fresh" -- do not fall back to `updated_at` for these fields.
A restoration guard should require the fields it depends on (e.g. affirmative
stock plus current price/shipping) to be both non-null and within its own
freshness window; this worker does not implement or modify that guard logic
(`app/services/ebay_revisions.py` is explicitly out of scope here and owned
by the parallel `freshness-guard-20260911` worker).

## Scope deliberately left out

- No changes to `app/services/ebay_revisions.py` or its tests (owned by the
  parallel freshness-guard worker; it may carry a temporary local copy of
  these columns until integration reconciles duplicate column definitions).
- No backfill of historical rows -- all pre-existing `SupplierProduct` rows
  get `NULL` observation timestamps after migration, by design (no
  trustworthy historical evidence exists per the follow-up doc).
- Did not touch Amazon/Home Depot capture-side "unknown stock" detection
  confidence (flagged in the follow-up doc as a separate, supplier-specific
  problem) -- this change only affects how the *presence* of an explicit
  capture value is turned into an observation timestamp, not whether a given
  supplier's scraper correctly detects stock state.
- No live/operational actions were taken; all tests run against disposable
  in-memory SQLite engines.

## Open questions for the coordinator

- Confirm the freshness guard's intended staleness window (the follow-up doc
  mentions 24 hours) and whether it should require *all three* fields fresh
  simultaneously, or only the ones relevant to the action being gated (e.g. a
  price update might not need fresh shipping evidence).
- Confirm reconciliation plan for any duplicate column definitions the
  freshness-guard worker's tests may have added locally, per the task
  instructions.
