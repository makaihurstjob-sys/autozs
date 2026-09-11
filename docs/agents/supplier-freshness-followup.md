# Supplier observation freshness follow-up

Report-only investigation at 092b393; no implementation, tests, operational database, or browser access. Independent review of restock result 379621f found the reported batch lifecycle issues resolved for normal existing-member paths. This report prepares the next round.

## Evidence and current gap

- `SupplierProduct` (apps/api/app/models/domain.py:202) has values plus generic TimestampMixin.updated_at, with no field-observation timestamps. Its in_stock default is True, which is not observation evidence.
- `import_captured_product` and `update_product_from_capture` in importer.py preserve missing stock, price and shipping inputs but refresh supplier.updated_at unconditionally (664-681 and 765-785). A title-only or price-only capture can therefore make old affirmative stock appear fresh to stock_restoration_block.
- Bulk importer at importer.py:530-542 sets in_stock=True unconditionally. It must not stamp an affirmative observation simply because it imports a row.
- PriceSnapshot (domain.py:575) records product-level price/shipping and generic timestamps, no stock or supplier-row identity. `_log_supplier_snapshot` (importer.py:1002) receives effective values that can be carried forward. Its timestamp cannot prove a new price/shipping observation.
- SourceRefreshJob.completed_at/captured_price indicates a refresh outcome, not explicit stock observation. SupplierDeliveryQuote.observed_at is real scoped delivery evidence, keyed by supplier/ZIP/quantity; it is not stock/price evidence for every listing destination.
- Capture schemas already accept nullable source_in_stock/source_price/detected shipping (schemas/domain.py:185/202). Home Depot capture sends deliveryAvailability, which can be unknown. Amazon capture sends !unavailable (capture.js:769), which currently treats absence of an unavailable indicator as positive; timestamps alone will not improve that detector's confidence.

## Smallest evidence-preserving change

Add nullable stock_observed_at, price_observed_at and shipping_observed_at to SupplierProduct. No defaults and no ORM onupdate. A single shared timestamp would again lose partial-capture provenance; independent nullable times let partial observations retain their real ages.

Centralize capture value updates with one server receipt time:

- Update stock timestamp only when source_in_stock is explicitly True or False; omitted/null stock leaves value and timestamp untouched.
- Update price timestamp only for a supplied finite positive price or explicit price-unavailable observation. Keep price_unavailable blocking restoration. A false price-unavailable flag alone does not establish a price observation.
- Update shipping timestamp only for an explicit shipping observation. An out-of-stock capture can invalidate shipping immediately, but must not establish affirmative shipping evidence.
- Ordinary metadata changes and bulk import defaults must never refresh these times. Source identity changes should clear observation times so evidence from a previous supplier URL cannot be reused.
- In stock_restoration_block require affirmative stock plus current valid price/shipping values and each required observation within 24 hours. Preserve quantity-zero paths and recording authoritative completed external actions. Do not weaken the check back to updated_at for legacy rows.

Timestamp confidence is limited to the incoming capture claim. Separately test/improve Amazon unknown-stock detection before describing a fresh True flag as affirmative UI proof.

## Migration and rollout

The project uses additive startup schema migration in apps/api/app/main.py:121-153. Add three nullable DATETIME columns there and in the ORM; exercise both an old disposable SQLite schema and a new schema. No trustworthy historical automatic backfill exists from updated_at, PriceSnapshot, or refresh completion. Leave legacy values intact and timestamps NULL, requiring a fresh capture before positive restoration. Do not set timestamps to migration time.

Expect pending restorations to be held/cancelled until refresh succeeds, while stock reductions remain executable. Populate through ordinary authorized source refresh and expose a specific missing/stale observation reason. Rollout needs coordinator-owned schema/application activation; this report authorizes no live changes.

## Acceptance cases for implementation

1. Title-only and price-only captures cannot refresh old stock; shipping-only cannot refresh price.
2. Complete explicit fresh capture enables a valid restock; missing/null/default True stock does not.
3. Negative stock or unavailable price blocks immediately; subsequent incomplete capture cannot resurrect old affirmative evidence.
4. Changing source identity clears observation validity; unrelated row edits leave observation times unchanged.
5. Legacy migration preserves values but leaves timestamps NULL; repeated startup migration is idempotent.
6. Queued CSV and prepared upload gates enforce the new timestamps, preserving safe reductions and confirmation recording.

Recommended next assignment: importer/model/startup migration plus isolated importer and revision regressions, with independent review of capture semantics. Keep source detector confidence changes bounded separately if they require supplier-specific redesign.
