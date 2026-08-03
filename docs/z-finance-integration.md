# AutoZS ↔ Z Finance integration

AutoZS never connects to Plaid. Z Finance is the only Plaid-facing system and
must expose only normalized accounts, transactions, and payouts. AutoZS never
accepts Plaid credentials, access tokens, webhooks, or raw provider payloads.

## Configuration

Configure these values in the deployment environment (never in source control):

- `AUTOZS_Z_FINANCE_TOKEN`: bearer token Z Finance sends to AutoZS.
- `Z_FINANCE_BASE_URL`: the clean HTTPS origin of Z Finance.
- `Z_FINANCE_AUTOZS_TOKEN`: bearer token AutoZS sends to Z Finance.
- `Z_FINANCE_OPERATING_ACCOUNT_ID`: the one permitted operating-bank account.
- `Z_FINANCE_PURCHASING_CARD_ID`: the one permitted purchasing card.

The two account IDs must be present and different. `Z_FINANCE_BASE_URL` rejects
HTTP, embedded credentials, paths, query strings, and fragments. Tokens are
never logged or returned.

## AutoZS endpoints

All four endpoints require `Authorization: Bearer
<AUTOZS_Z_FINANCE_TOKEN>`. An absent server token returns 503. A missing or
incorrect bearer token returns 401 with `WWW-Authenticate: Bearer`.

- `GET /api/z-finance/summary`
- `GET /api/z-finance/orders`
- `GET /api/z-finance/payouts`
- `POST /api/z-finance/sync`

GET endpoints accept `period=all|monthly|weekly|custom`, `startDate`, and
`endDate`. Custom periods require both dates. Weekly periods begin Monday.

Sync accepts:

```json
{"startDate":"2026-07-01","endDate":"2026-07-31","resetCursor":false}
```

## Z Finance endpoints consumed by AutoZS

- `GET /integrations/autozs/accounts`
- `GET /integrations/autozs/transactions?cursor=&startDate=&endDate=`

Responses may be direct arrays or wrapped in `data`, `accounts`,
`transactions`, and `payouts`. Only the two configured account IDs are
persisted. Missing balances mark an account stale and are returned as `null`;
AutoZS never invents a zero balance. A pagination cursor is committed only
after its page is durably imported and reconciled.

## Accounting and reconciliation

Orders and supplier orders remain the P&L source of truth. Financial
transactions reconcile those records and supply normalized eBay fees, refunds,
subscriptions, payouts, transfers, and card payments. Transfers and card
payments never affect P&L.

Supplier charges match only by an exact supplier-order reference and amount, or
by one unique exact-amount supplier order within three days. Payouts use the
same explicit-reference-first and unique exact-amount/date rule. Merchant and
category guesses are prohibited. Ambiguous or unmatched transactions remain
`needs_review` and are excluded from P&L.

The API uses `a.m.anim-59` as the default store key. Other non-empty store keys
remain distinct. Responses contain no buyer names, addresses, payment details,
or raw provider data.
