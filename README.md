# AutoZS

Local MVP for eBay product research, candidate approval, manual supplier monitoring, repricing, and sandbox order workflow.

## Start

If Docker is installed:

```bash
cp .env.example .env
docker compose up --build
```

If Docker/Node is not installed, use the Python fallback:

```bash
/Users/makaihurst/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/dev_local.py
```

Open:

- Web dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs

## Windows Operations Server

For always-on production testing, run AutoZS on the Windows machine and point the Mac dashboard at it over the LAN:

```text
http://127.0.0.1:3000/?api=http://WINDOWS_IP:8000
```

Recommended first Windows `.env` shape:

```env
AUTOZS_WORKER_ID=windows-main
AUTOZS_WORKER_LABEL=Windows Store Server
AUTOZS_WORKER_ROLE=operations
DATABASE_URL=sqlite:///C:/AutoZS/data/autozs.db
AUTOZS_CHROME_EXECUTABLE_PATH=C:/Program Files/Google/Chrome/Application/chrome.exe
AUTOZS_CHROME_PROFILE_ROOT=C:/AutoZS/chrome-profiles
AUTOZS_EBAY_PROFILE_ROOT=C:/AutoZS/chrome-profiles/ebay
AUTOZS_HOME_DEPOT_PROFILE_ROOT=C:/AutoZS/chrome-profiles/home-depot
```

The API registers a worker heartbeat at startup and every minute after that. The dashboard header shows whether the operations worker is online, stale, or offline, and `Settings -> Supplier Settings -> System` shows the database URL plus Chrome/profile paths. Do not store eBay or supplier passwords in AutoZS; keep sign-in state inside the Chrome profiles.

## Static Dashboard / Netlify

The dashboard in `apps/local_dashboard` is static and can be deployed to Netlify with the included `netlify.toml`.

Netlify only hosts the frontend. The FastAPI backend still needs to be running somewhere reachable from the browser. After deploying, open the site once with an API URL query string:

```text
https://your-site.netlify.app/?api=https://your-api.example.com
```

Or use `Settings -> api_base_url` in the dashboard. The value is saved in the browser so the same Netlify dashboard can keep talking to your backend.

## Current V1 Behavior

- Product research accepts competitor or keyword scans and creates deterministic mock candidates.
- Candidates must be approved before becoming products.
- Home Depot imports start from pasted source URLs in the dashboard. When Home Depot blocks server-side scraping, the dashboard opens the product pages with extension auto-import enabled; the Chrome extension adds an `Import to Website` button directly below the Home Depot header and captures visible title, price, shipping, description bullets, and images from the real browser page.
- Supplier matching is manual for non-captured products. Attach a Home Depot example URL and price on the Products page when needed.
- Repricing calculates floor and suggested prices without writing to live eBay.
- The Price Monitor page can create a resumable browser-capture batch. `Test refresh 5` forces a five-product pilot; `Run next due 25` only queues products whose supplier capture is older than the configured interval. The default source refresh interval is six hours.
- A refresh batch leases one product at a time for ten minutes and advances through the batch in one Chrome tab. Price changes are recorded and eligible live eBay listings receive queued revision jobs; eBay writes remain separately gated.
- Docker Compose runs Celery Beat for the catalog calculation cycle. `CATALOG_AUTOMATION_INTERVAL_MINUTES` defaults to 360 minutes, but this calculation cycle does not replace supplier browser capture.
- Orders are sandbox/mock imported through the Orders page.
- eBay write actions are disabled unless `EBAY_ENABLE_WRITES=true`. The Settings screen can start the eBay OAuth consent flow, exchange the returned authorization code for sandbox/production user tokens, and refresh the access token. API-ready products can be published to eBay Sandbox through the Inventory API only after OAuth, category/location/policy settings, and the write gate are all configured.

## eBay Sandbox Connection

1. Create an eBay developer app and copy its sandbox Client ID, Client Secret, and RuName/Redirect URI.
2. In `Settings`, save `ebay_environment=sandbox`, `ebay_client_id`, `ebay_client_secret`, and `ebay_redirect_uri`.
3. Click `Start eBay OAuth`. The dashboard copies and opens the consent URL.
4. After eBay redirects back, paste the full redirect URL or just the `code` into `authorization code`, then click `Finish OAuth`.
5. Use `Refresh Access Token` when the short-lived access token expires.

This stores tokens locally in the app settings table or `.env` fallback values. The OAuth request includes Inventory API scope so the sandbox publish path can work, but the app still refuses listing writes until `ebay_enable_writes=true`.

## Multi-Account Support

Use `Settings -> eBay Account Profiles` to create one profile per seller account, such as `buyclassy-sandbox` or `outlet-sandbox`. Profiles store app keys, OAuth tokens, marketplace/category/location/policy IDs, and a per-account write gate. Do not store eBay passwords in the app; connect accounts through OAuth tokens instead.

## Useful Commands

```bash
cd apps/api && pytest
cd apps/web && npm install && npm run build
```

## Next Real Integrations

1. Replace mock research with eBay Browse/Finding-style API calls.
2. Add sandbox listing/order imports.
3. Add production listing safeguards after sandbox publishing is proven.
4. Replace manual supplier price entry with allowed supplier data adapters.
5. Expand Celery Beat schedules from the catalog cycle into recurring scans, source refresh queues, and order sync.
