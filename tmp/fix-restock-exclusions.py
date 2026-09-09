from pathlib import Path
p=Path('apps/api/app/services/orders.py');s=p.read_text(encoding='utf-8');s=s.replace('    if listing is None:\n        listing = db.scalar(', '    if listing is None and not item_number:\n        listing = db.scalar(',1);s=s.replace('    listing.status = "ended"\n\n    _queue_replacement_publish', '    if listing.status not in ("scheduled", "listed", "live", "active", "ended"):\n        return\n    listing.status = "ended"\n\n    _queue_replacement_publish',1);needle='    checked_at = now or datetime.utcnow()\n    supplier = product.supplier_products[0] if product.supplier_products else None';repl='''    from app.services.listing_exclusions import listing_exclusion_reason

    if product.status == ProductStatus.deleted.value or listing_exclusion_reason(db, product.id):
        return False
    checked_at = now or datetime.utcnow()
    supplier = product.supplier_products[0] if product.supplier_products else None''';assert needle in s;s=s.replace(needle,repl);p.write_text(s,encoding='utf-8')
