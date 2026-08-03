from datetime import datetime, timezone


def test_finance_overview_tracks_accounts_subscriptions_and_expenses(client) -> None:
    bank = client.post(
        "/finance/accounts",
        json={
            "provider": "plaid_bridge",
            "external_id": "bank-001",
            "account_type": "bank",
            "name": "Business checking",
            "mask": "4321",
            "current_balance": 1250.0,
            "available_balance": 1200.0,
        },
    )
    assert bank.status_code == 200

    ebay = client.post(
        "/finance/accounts",
        json={
            "provider": "ebay_chrome",
            "external_id": "a.m.anim-59",
            "account_type": "ebay",
            "name": "a.m.anim-59 eBay funds",
            "current_balance": 125.0,
            "available_balance": 75.0,
            "held_balance": 50.0,
        },
    )
    assert ebay.status_code == 200

    subscription = client.post(
        "/finance/subscriptions",
        json={"name": "AutoZS hosting", "amount": 20.0, "cadence": "monthly"},
    )
    assert subscription.status_code == 200

    imported = client.post(
        "/finance/entries/import",
        json=[
            {
                "provider": "plaid_bridge",
                "external_id": "transaction-001",
                "financial_account_id": bank.json()["id"],
                "entry_type": "expense",
                "category": "software",
                "amount": -20.0,
                "description": "AutoZS hosting",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    ).json()
    assert imported["imported"] == 1

    overview = client.get("/finance/overview").json()
    assert overview["bank_balance"] == 1250.0
    assert overview["ebay_available"] == 75.0
    assert overview["ebay_held"] == 50.0
    assert overview["operating_expenses"] == 20.0
    assert overview["subscriptions"][0]["name"] == "AutoZS hosting"
    assert overview["periods"][0]["period"] == "All time"
