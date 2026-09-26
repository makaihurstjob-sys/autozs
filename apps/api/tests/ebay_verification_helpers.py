from datetime import datetime, timezone


def verify_queued(client):
    identity = client.get("/supplier-orders/ebay-verification-next").json()
    assert identity is not None
    return client.post(f"/supplier-orders/{identity['supplier_order_id']}/ebay-verification", json={
        "ebay_order_id": identity["ebay_order_id"], "account_key": identity["account_key"],
        "source_url": "https://www.ebay.com/mesh/ord/details?mode=SH&orderid=" + identity["ebay_order_id"],
        "status": "eligible", "observed_at": datetime.now(timezone.utc).isoformat(),
        "evidence": "Paid. Ship by Sep 28. No cancellation or refund. Awaiting shipment."})
