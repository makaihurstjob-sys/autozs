from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.api import routes
from app.services import z_finance


def _settings(**overrides):
    values = {
        "autozs_z_finance_token": "server-secret",
        "z_finance_base_url": "https://finance.example.test",
        "z_finance_autozs_token": "client-secret",
        "z_finance_operating_account_id": "bank-1",
        "z_finance_purchasing_card_id": "card-1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_z_finance_endpoints_require_separate_bearer(client, monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_settings", lambda: _settings())
    monkeypatch.setattr(z_finance, "get_settings", lambda: _settings())

    missing = client.get("/api/z-finance/summary")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"

    wrong = client.get("/api/z-finance/summary", headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 401

    accepted = client.get(
        "/api/z-finance/summary",
        headers={"Authorization": "Bearer server-secret"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["store_key"] == "a.m.anim-59"
    assert "realized_net_profit_loss" in accepted.json()
    assert "credit_card_balance" in accepted.json()


def test_z_finance_missing_server_token_returns_503(client, monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_settings", lambda: _settings(autozs_z_finance_token=""))
    response = client.get("/api/z-finance/orders")
    assert response.status_code == 503


def test_z_finance_custom_period_validation(client, monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_settings", lambda: _settings())
    response = client.get(
        "/api/z-finance/summary?period=custom&startDate=2026-07-01",
        headers={"Authorization": "Bearer server-secret"},
    )
    assert response.status_code == 422

    start, end = z_finance.period_bounds("weekly", None, date(2026, 7, 30))
    assert start.date().isoformat() == "2026-07-27"
    assert end.date().isoformat() == "2026-07-30"


@pytest.mark.parametrize(
    "url",
    [
        "http://finance.example.test",
        "https://user:pass@finance.example.test",
        "https://finance.example.test/path",
        "https://finance.example.test?token=no",
        "https://finance.example.test/#fragment",
    ],
)
def test_z_finance_rejects_unclean_base_urls(url) -> None:
    with pytest.raises(ValueError):
        z_finance.validate_client_config(_settings(z_finance_base_url=url))


def test_z_finance_requires_distinct_allowlisted_accounts() -> None:
    with pytest.raises(ValueError):
        z_finance.validate_client_config(
            _settings(z_finance_purchasing_card_id="bank-1")
        )


def test_store_keys_default_to_canonical_and_keep_other_stores_distinct() -> None:
    assert z_finance.normalize_store_key(None) == "a.m.anim-59"
    assert z_finance.normalize_store_key("a.m.anim-59") == "a.m.anim-59"
    assert z_finance.normalize_store_key("second-store") == "second-store"


def test_client_validates_wrapped_accounts_and_exact_bearer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer client-secret"
        return httpx.Response(
            200,
            json={
                "data": {
                    "storeKey": "a.m.anim-59",
                    "accounts": [
                        {"id": "bank-1", "name": "Operating", "type": "bank", "currency": "USD"},
                        {"id": "card-1", "name": "Purchasing", "type": "credit", "currency": "USD"},
                    ],
                }
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    finance_client = z_finance.ZFinanceClient(
        "https://finance.example.test",
        "client-secret",
        {"bank-1", "card-1"},
        client=http_client,
    )
    assert len(finance_client.get_accounts()) == 2
    http_client.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"accounts": [{"id": "bank-1"}, {"id": "unexpected"}]},
        {"storeKey": "some-other-store", "accounts": [{"id": "bank-1"}, {"id": "card-1"}]},
        {"accounts": [{"id": "bank-1", "accessToken": "prohibited"}, {"id": "card-1"}]},
        {"accounts": [{"id": "bank-1", "rawProvider": {}}, {"id": "card-1"}]},
    ],
)
def test_client_rejects_account_contract_violations(payload) -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    )
    finance_client = z_finance.ZFinanceClient(
        "https://finance.example.test",
        "client-secret",
        {"bank-1", "card-1"},
        client=http_client,
    )
    with pytest.raises(ValueError):
        finance_client.get_accounts()
    http_client.close()


def test_transaction_client_follows_cursor_only_when_has_more() -> None:
    requested_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        requested_cursors.append(cursor)
        transaction = {
            "id": f"tx-{len(requested_cursors)}",
            "accountId": "bank-1",
            "amount": 1.0,
            "direction": "inflow",
            "classification": "payout",
            "postedAt": "2026-07-29T12:00:00Z",
            "pending": False,
            "currency": "USD",
            "storeKey": "a.m.anim-59",
        }
        if cursor is None:
            return httpx.Response(
                200,
                json={"transactions": [transaction], "hasMore": True, "nextCursor": "page-2"},
            )
        return httpx.Response(
            200,
            json={"transactions": [transaction], "hasMore": False, "nextCursor": "ignored"},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    finance_client = z_finance.ZFinanceClient(
        "https://finance.example.test",
        "client-secret",
        {"bank-1", "card-1"},
        client=http_client,
    )
    pages = list(
        finance_client.iter_transaction_pages(
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 30),
        )
    )
    assert len(pages) == 2
    assert requested_cursors == [None, "page-2"]
    http_client.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("accountId", "unexpected"),
        ("direction", "credit"),
        ("classification", "unknown"),
        ("storeKey", "some-other-store"),
    ],
)
def test_transaction_client_rejects_isolation_and_schema_violations(field, value) -> None:
    transaction = {
        "id": "tx-1",
        "accountId": "bank-1",
        "amount": 1.0,
        "direction": "outflow",
        "classification": "supplier_charge",
        "postedAt": "2026-07-29T12:00:00Z",
        "pending": False,
        "currency": "USD",
        "storeKey": "a.m.anim-59",
    }
    transaction[field] = value
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"transactions": [transaction], "hasMore": False},
            )
        )
    )
    finance_client = z_finance.ZFinanceClient(
        "https://finance.example.test",
        "client-secret",
        {"bank-1", "card-1"},
        client=http_client,
    )
    with pytest.raises(ValueError):
        list(finance_client.iter_transaction_pages())
    http_client.close()


def test_sync_endpoint_schema_without_remote_sync(client, monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_settings", lambda: _settings())
    called = {"value": False}

    def fake_sync(_db, **values):
        called["value"] = True
        assert values["start_date"] == date(2026, 7, 1)
        assert values["end_date"] == date(2026, 7, 2)
        return {
            "accounts_processed": 2,
            "transactions_processed": 0,
            "payouts_processed": 0,
            "cursor": None,
            "synced_at": None,
        }

    monkeypatch.setattr(routes, "sync_from_z_finance", fake_sync)
    unauthorized = client.post(
        "/api/z-finance/sync",
        json={"startDate": "2026-07-01", "endDate": "2026-07-02"},
    )
    assert unauthorized.status_code == 401
    accepted = client.post(
        "/api/z-finance/sync",
        headers={"Authorization": "Bearer server-secret"},
        json={"startDate": "2026-07-01", "endDate": "2026-07-02", "resetCursor": False},
    )
    assert accepted.status_code == 200
    assert accepted.json()["accounts_processed"] == 2
    assert called["value"] is True
