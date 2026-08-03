def test_customer_conversation_import_and_human_reply_queue(client) -> None:
    conversation = client.post(
        "/customer-service/conversations/import",
        json={
            "account_id": "a.m.anim-59",
            "ebay_thread_id": "thread-001",
            "buyer_username": "happy-buyer",
            "subject": "Question about my order",
            "messages": [
                {
                    "external_message_id": "message-001",
                    "direction": "inbound",
                    "origin": "buyer",
                    "body": "When will this ship?",
                }
            ],
        },
    ).json()

    assert conversation["buyer_username"] == "happy-buyer"
    assert conversation["messages"][0]["origin"] == "buyer"

    reply = client.post(
        f"/customer-service/conversations/{conversation['id']}/messages",
        json={"body": "Thanks for checking in. We are preparing it now.", "origin": "human"},
    ).json()
    assert reply["status"] == "queued"
    assert reply["origin"] == "human"

    claimed = client.post("/customer-service/messages/next").json()
    assert claimed["id"] == reply["id"]
    assert claimed["status"] == "sending"

    sent = client.patch(
        f"/customer-service/messages/{reply['id']}",
        json={"status": "sent", "external_message_id": "message-002"},
    ).json()
    assert sent["status"] == "sent"
    assert sent["sent_at"]


def test_customer_message_import_is_idempotent(client) -> None:
    payload = {
        "account_id": "a.m.anim-59",
        "ebay_thread_id": "thread-repeat",
        "buyer_username": "repeat-buyer",
        "subject": "Repeated sync",
        "messages": [
            {
                "external_message_id": "message-repeat",
                "direction": "inbound",
                "origin": "buyer",
                "body": "This should import once.",
            }
        ],
    }
    client.post("/customer-service/conversations/import", json=payload)
    repeated = client.post("/customer-service/conversations/import", json=payload).json()

    assert len(repeated["messages"]) == 1


def test_customer_template_library_renders_placeholders(client) -> None:
    templates = client.get("/customer-service/templates").json()
    assert len(templates) == 42
    assert {template["category"] for template in templates} == {
        "Post-Sales General",
        "Returns",
        "Item Delivery",
        "Cancellations",
        "Pre-Sales",
    }
    post_sale = next(template for template in templates if template["key"] == "post_sale_thank_you")
    assert post_sale["automation"] == "automatic"

    preview = client.post(
        "/customer-service/templates/address_change_already_shipped/render",
        json={
            "variables": {
                "buyer_first_name": "Jamie",
                "seller_first_name": "Makail",
                "tracking_number": "1Z999",
                "shipping_carrier": "UPS",
            }
        },
    ).json()
    assert preview["unresolved_placeholders"] == []
    assert "Jamie" in preview["rendered_body"]
    assert "1Z999" in preview["rendered_body"]


def test_quick_reply_template_requires_fields_and_manual_review(client) -> None:
    conversation = client.post(
        "/customer-service/conversations/import",
        json={
            "account_id": "a.m.anim-59",
            "ebay_thread_id": "thread-template",
            "buyer_username": "Jamie",
            "subject": "Address request",
            "messages": [
                {
                    "external_message_id": "message-template",
                    "direction": "inbound",
                    "origin": "buyer",
                    "body": "Can I change the address?",
                }
            ],
        },
    ).json()
    endpoint = (
        f"/customer-service/conversations/{conversation['id']}/template-messages"
        "?template_key=address_change_already_shipped"
    )
    missing = client.post(
        endpoint,
        json={"variables": {"seller_first_name": "Makail"}},
    )
    assert missing.status_code == 422
    assert "tracking_number" in missing.json()["detail"]

    automatic = client.post(
        endpoint,
        json={
            "origin": "automatic",
            "variables": {
                "buyer_first_name": "Jamie",
                "seller_first_name": "Makail",
                "tracking_number": "1Z999",
                "shipping_carrier": "UPS",
            },
        },
    )
    assert automatic.status_code == 422
    assert "human review" in automatic.json()["detail"]

    queued = client.post(
        endpoint,
        json={
            "variables": {
                "buyer_first_name": "Jamie",
                "seller_first_name": "Makail",
                "tracking_number": "1Z999",
                "shipping_carrier": "UPS",
            },
        },
    ).json()
    assert queued["status"] == "queued"
    assert queued["origin"] == "human"
    assert "1Z999" in queued["body"]


def test_quick_reply_never_uses_ebay_username_as_buyer_first_name(client) -> None:
    conversation = client.post(
        "/customer-service/conversations/import",
        json={
            "account_id": "a.m.anim-59",
            "ebay_thread_id": "thread-no-recipient-name",
            "buyer_username": "not-the-buyers-name-123",
            "subject": "Order update",
            "messages": [
                {
                    "external_message_id": "message-no-recipient-name",
                    "direction": "inbound",
                    "origin": "buyer",
                    "body": "Any update?",
                }
            ],
        },
    ).json()
    endpoint = (
        f"/customer-service/conversations/{conversation['id']}/template-messages"
        "?template_key=address_change_already_shipped"
    )
    response = client.post(
        endpoint,
        json={
            "variables": {
                "seller_first_name": "Makail",
                "tracking_number": "1Z999",
                "shipping_carrier": "UPS",
            },
        },
    )
    assert response.status_code == 422
    assert "buyer_first_name" in response.json()["detail"]
    assert "not-the-buyers-name-123" not in response.text


def test_post_sale_automation_backfills_each_order_once(client) -> None:
    client.post(
        "/products/import-captured",
        json={
            "source_url": "https://www.homedepot.com/p/Customer-Message-Test/121212",
            "title": "Customer Message Test Product",
            "source_price": 10.0,
            "source_shipping": 0.0,
        },
    )
    client.post("/orders/sync-sandbox")

    first = client.post("/customer-service/automation/post-sale").json()
    second = client.post("/customer-service/automation/post-sale").json()
    conversations = client.get("/customer-service/conversations").json()

    assert first["queued"] == 1
    assert second["queued"] == 0
    assert conversations[0]["messages"][0]["origin"] == "automatic"
    assert conversations[0]["messages"][0]["status"] == "queued"
    assert "Thank you for your purchase" in conversations[0]["messages"][0]["body"]
