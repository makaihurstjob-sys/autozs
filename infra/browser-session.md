# Browser Session Capture

Home Depot is blocking direct server-side requests from the FastAPI importer with `403 Access Denied`.
The lowest-cost next step is a persistent local browser session:

1. Open the Home Depot URL in a real browser automation profile.
2. Let that profile keep cookies, ZIP/location state, and any normal browsing session data.
3. Extract title, visible price, description bullets, and image URLs from the rendered page.
4. Post the captured payload back to the local API.

This is closer to how supplier-monitoring tools work than plain `httpx` scraping.

## Install Optional Browser Runtime

```bash
/Users/makaihurst/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pip install -r apps/api/requirements-browser.txt
/Users/makaihurst/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m playwright install chromium
```

## Capture One Product

Keep the dashboard/API running first:

```bash
/Users/makaihurst/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/dev_local.py
```

Then in another terminal:

```bash
/Users/makaihurst/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/capture_home_depot.py \
  "https://www.homedepot.com/p/Milwaukee-REDLITHIUM-Lithium-Ion-Rechargeable-USB-3-0-AH-Battery-48-11-2131/313303644"
```

Use `--pause` if the page asks for location, blocks, or needs manual review:

```bash
/Users/makaihurst/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/capture_home_depot.py --pause "HOME_DEPOT_URL"
```

The browser profile is saved under `.browser-profile/home-depot`, so later runs reuse cookies and location state.

## Add Shipping Or Competitor Price

```bash
/Users/makaihurst/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/capture_home_depot.py \
  --shipping 55 \
  --competitor 149.99 \
  "HOME_DEPOT_URL"
```

## Proxy Trial

Only after the persistent local browser still fails, test a proxy:

```bash
/Users/makaihurst/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/capture_home_depot.py \
  --proxy-server "http://user:pass@proxy-host:proxy-port" \
  --pause \
  "HOME_DEPOT_URL"
```

For cost control, avoid starting with a large proxy subscription. Test one small plan or trial, measure the success rate, and keep cached snapshots so the app does not re-check every product constantly.

## Practical Notes

- Proxies do not replace parsing. We still need robust extraction logic.
- Residential proxies are more likely to work than datacenter proxies, but they cost more.
- A persistent browser profile is cheaper and should be tried before proxies.
- For scale, cache last known price and only refresh products on a schedule or when they are close to selling.
- Avoid retailer checkout automation. This capture path only reads product data and posts it to the local app.
