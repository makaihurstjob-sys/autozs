"""Exact approval and dry run tests use disposable SQLite and synthetic sales only."""
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_purchase_submission import ready, quote
from test_purchase_budget import engine
from app.models.domain import AppSetting, SupplierOrder, PurchaseReservation, SupplierPurchaseAttempt
from app.services.purchase_approval import review, require_approval, history
from app.services.purchase_submission import authorize_submission
from app.services.fulfillment import approve_supplier_order, claim_next_supplier_order, update_supplier_order


def test_dry_run_never_reserves_or_grants_click_permission(ready):
    with Session(ready) as db:
        result = authorize_submission(db, 1, "test-token", quote(), dry_run=True)
        assert result == dict(authorized=False, dry_run=True, supplier_order_id=1, total_cents=1000)
        assert db.scalar(select(PurchaseReservation)) is None
        assert not any(e["event"] == "submission_requested" for e in history(db, 1))
        assert require_approval(db, db.get(SupplierOrder, 1))


@pytest.mark.parametrize("field,value", [("supplier", "lowes"), ("order_id", 2),
    ("total", 11), ("shipping_cost", 2), ("address_line1", "Different test destination")])
def test_changed_plan_cannot_spend_under_previous_approval(ready, field, value):
    with Session(ready) as db:
        setattr(db.get(SupplierOrder, 1), field, value)
        db.commit()
        with pytest.raises(ValueError):
            authorize_submission(db, 1, "test-token", quote())
        db.rollback()
        assert db.scalar(select(PurchaseReservation)) is None


@pytest.mark.parametrize("field,value", [("title", "Different fixture item"), ("quantity", 2),
    ("unit_price", 9), ("source_url", "https://www.homedepot.com/p/Other/654321")])
def test_changed_item_invalidates_approval(ready, field, value):
    with Session(ready) as db:
        setattr(db.get(SupplierOrder, 1).items[0], field, value)
        db.commit()
        with pytest.raises(ValueError):
            authorize_submission(db, 1, "test-token", quote())
        db.rollback()
        assert db.scalar(select(PurchaseReservation)) is None


@pytest.mark.parametrize("changes", [dict(total="11", tax="2"), dict(total="9", tax="0"),
    dict(items=[dict(source_url="https://www.homedepot.com/p/Other/654321", quantity=1, unit_price=8)]),
    dict(items=[dict(source_url="https://www.homedepot.com/p/Test/123456", quantity=2, unit_price=4)])])
def test_changed_live_checkout_cannot_spend(ready, changes):
    with Session(ready) as db:
        with pytest.raises(ValueError):
            authorize_submission(db, 1, "test-token", quote(**changes))
        db.rollback()
        assert db.scalar(select(PurchaseReservation)) is None


def test_expired_approval_requires_new_deliberate_click(ready):
    with Session(ready) as db:
        entry = db.scalar(select(AppSetting).where(AppSetting.key.startswith("purchase_approval:1:")))
        value = json.loads(entry.value)
        value["expires_at"] = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
        entry.value = json.dumps(value)
        db.commit()
        with pytest.raises(ValueError, match="expired"):
            authorize_submission(db, 1, "test-token", quote())
        db.rollback()
        assert db.scalar(select(PurchaseReservation)) is None


def test_stale_review_is_rejected_and_does_not_create_new_approval(ready, monkeypatch):
    monkeypatch.setattr("app.services.fulfillment._readiness_issues", lambda row: [])
    with Session(ready) as db:
        row = db.get(SupplierOrder, 1)
        old = review(row)
        row.status = "draft"
        row.shipping_cost, row.total = 2, 11
        db.commit()
        with pytest.raises(ValueError, match="changed"):
            approve_supplier_order(db, 1, owner_click=True, fingerprint=old["fingerprint"])
        db.rollback()
        assert len(history(db, 1)) == 1


def test_concurrent_final_workers_get_only_one_permission(ready):
    barrier = Barrier(2)
    def attempt(_):
        barrier.wait()
        with Session(ready) as db:
            try:
                return authorize_submission(db, 1, "test-token", quote())["authorized"]
            except ValueError:
                db.rollback()
                return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [False, True]
    with Session(ready) as db:
        assert len(db.scalars(select(PurchaseReservation)).all()) == 1
        assert len([e for e in history(db, 1) if e["event"] == "submission_requested"]) == 1


def test_double_approval_does_not_create_another_version(ready, monkeypatch):
    monkeypatch.setattr("app.services.fulfillment._readiness_issues", lambda row: [])
    with Session(ready) as db:
        row = db.get(SupplierOrder, 1)
        row.status = "draft"
        db.commit()
        fingerprint = review(row)["fingerprint"]
    barrier = Barrier(2)
    def attempt(_):
        barrier.wait()
        with Session(ready) as db:
            return approve_supplier_order(db, 1, owner_click=True, fingerprint=fingerprint).status
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(attempt, range(2))) == ["queued", "queued"]
    with Session(ready) as db:
        # One fixture approval plus one new approval; the duplicate is idempotent.
        assert len([e for e in history(db, 1) if e["event"] == "approved"]) == 2


def test_audit_records_outcome_without_buyer_or_payment_details(ready):
    with Session(ready) as db:
        authorize_submission(db, 1, "test-token", quote())
        update_supplier_order(db, db.get(SupplierOrder, 1), {"status": "failed", "failure_reason": "Fixture checkout challenge"})
        events = history(db, 1)
        assert [e["event"] for e in events] == ["approved", "submission_requested", "outcome"]
        assert events[-1]["status"] == "failed"
        assert set().union(*(e.keys() for e in events)) <= {"event", "at", "approval_id", "reservation_id", "status"}
        assert db.scalar(select(PurchaseReservation)).status == "uncertain"


def test_approval_route_rejects_missing_review_and_other_origins(client):
    from test_fulfillment import _prepare_order
    row = _prepare_order(client).json()
    route = f"/supplier-orders/{row['id']}"
    owner_headers = {"Origin": "http://127.0.0.1:3000", "X-AutoZS-Owner-Action": "place-order"}
    assert client.post(route + "/place-order", headers=owner_headers).status_code == 422
    plan = client.get(route + "/approval-review").json()
    assert client.post(route + "/place-order", json={"fingerprint": plan["fingerprint"]},
        headers={**owner_headers, "Origin": "https://example.com"}).status_code == 403
    assert client.post(route + "/place-order", json={"fingerprint": "0" * 64}, headers=owner_headers).status_code == 422
    assert client.post(route + "/place-order", json={"fingerprint": plan["fingerprint"]}, headers=owner_headers).status_code == 200
    assert client.post(route + "/place-order", json={"fingerprint": plan["fingerprint"]}, headers=owner_headers).status_code == 409
    assert len(client.get(route + "/approval-history").json()) == 1
    assert "recipient_name" not in plan["snapshot"]
    assert "address_line1" not in plan["snapshot"]


def test_approval_phone_notices_use_existing_subscriptions_and_dedupe(ready, monkeypatch):
    from app.services import push_notifications as push
    monkeypatch.setattr(push, "get_push_config", lambda: {"enabled": True, "public_key": "test-key"})
    delivered = []
    monkeypatch.setattr(push, "_send_payload", lambda subscription, payload: delivered.append(payload))
    with Session(ready) as db:
        row = db.get(SupplierOrder, 1)
        row.status = "draft"
        db.commit()
        assert push.dispatch_purchase_approval_notifications(db)["sent"] == 0
        push.upsert_push_subscription(db, endpoint="https://push.example/test", p256dh="synthetic", auth="synthetic", vapid_public_key="test-key")
        assert push.dispatch_purchase_approval_notifications(db)["sent"] == 1
        assert push.dispatch_purchase_approval_notifications(db)["sent"] == 0
        row.shipping_cost, row.total = 2, 11
        db.commit()
        assert push.dispatch_purchase_approval_notifications(db)["sent"] == 1
        row.order.account_id = "sandbox"
        row.shipping_cost, row.total = 3, 12
        db.commit()
        assert push.dispatch_purchase_approval_notifications(db)["sent"] == 0
        assert delivered[0]["url"] == "/?view=orders"
        assert "Nothing is bought without your approval" in delivered[0]["body"]
        assert not any(key in json.dumps(delivered) for key in ("recipient_name", "address_line1", "card_number"))


def test_unconfigured_phone_notifications_stay_disabled(ready, monkeypatch):
    from app.services import push_notifications as push
    monkeypatch.setattr(push, "get_push_config", lambda: {"enabled": False})
    monkeypatch.setattr(push, "_send_payload", lambda *args: pytest.fail("Must not send"))
    with Session(ready) as db:
        assert push.dispatch_purchase_approval_notifications(db)["sent"] == 0


def test_changed_quote_is_reprepared_without_purchase_permission(ready, monkeypatch):
    from app.services.purchase_submission import stage_changed_quote
    monkeypatch.setattr("app.services.fulfillment._readiness_issues", lambda row: [])
    with Session(ready) as db:
        result = stage_changed_quote(db, 1, "test-token", quote(tax="2", total="11"))
        assert result == dict(authorized=False, new_approval_required=True, supplier_order_id=1)
        row = db.get(SupplierOrder, 1)
        assert row.status == "draft" and row.total == 11 and row.sales_tax == 2
        assert row.approved_at is None and row.approved_total == 0 and not row.checkout_token
        assert db.scalar(select(PurchaseReservation)) is None
        with pytest.raises(ValueError):
            require_approval(db, row)
        db.rollback()
        assert review(row)["snapshot"]["total_cents"] == 1100
        approved = approve_supplier_order(db, 1, owner_click=True, fingerprint=review(row)["fingerprint"])
        assert approved.status == "queued" and approved.approved_total == 11


@pytest.mark.parametrize("changes", [dict(items=[dict(source_url="https://www.homedepot.com/p/Other/654321",quantity=1,unit_price=8)]),
    dict(total="20"), dict(source_url="https://example.com/checkout"),
    dict(observed_at=datetime(2020,1,1))])
def test_changed_quote_cannot_replace_item_or_accept_unverified_costs(ready, changes):
    from app.services.purchase_submission import stage_changed_quote
    with Session(ready) as db:
        with pytest.raises(ValueError):
            stage_changed_quote(db, 1, "test-token", quote(**changes))
        db.rollback()
        assert db.get(SupplierOrder,1).total == 10
        assert db.scalar(select(PurchaseReservation)) is None


def test_post_submission_quote_cannot_reopen_a_purchase(ready):
    from app.services.purchase_submission import stage_changed_quote
    with Session(ready) as db:
        authorize_submission(db, 1, "test-token", quote())
        with pytest.raises(ValueError, match="reserved"):
            stage_changed_quote(db, 1, "test-token", quote(tax="2",total="11"))
        db.rollback()
        assert db.get(SupplierOrder,1).total == 10
        assert db.scalar(select(PurchaseReservation)).status == "submitting"
