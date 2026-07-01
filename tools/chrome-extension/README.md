# Chrome Source Capture Extension

Use this when Home Depot works in your normal Chrome browser but blocks server requests or Playwright-controlled browsers.

## Load The Extension

1. Open Chrome.
2. Go to `chrome://extensions`.
3. Turn on `Developer mode`.
4. Click `Load unpacked`.
5. Select this folder:

```text
/Users/makaihurst/Documents/Documents - Dane’s MacBook Air M3/eBay Automatic Dropshipping System/tools/chrome-extension
```

Chrome will show a `debugger` permission warning when the extension is reloaded. AutoZS uses it only during a requested eBay fill action to send browser-native typing or a click to the focused eBay field, then detaches immediately. It does not inspect passwords, cookies, or account data.

The extension also requests `downloads` and `storage` permissions for Seller Hub report synchronization. During a Sync Now run it tags the eBay report filename with the selected store and run ID, saves it under `~/Downloads/AutoZS`, and remembers only the active report run while the download finishes.

## Capture A Product

1. Make sure the local app is running at `http://127.0.0.1:3000`.
2. Open a Home Depot product page in normal Chrome.
3. Confirm the price is visible.
4. Click the `Import to Website` bar that appears directly below the Home Depot header. If the dashboard opened the page with `ea_auto_import=1`, the extension will try to import automatically after the page data loads.

The popup still has `Capture Into App` as a fallback, but the on-page button is the normal workflow. After import, the extension also asks the local app to download the captured image URLs into the product's local image folder.

The extension reads the current tab and posts the product payload to:

```text
http://127.0.0.1:8000/products/import-captured
```

This keeps capture free and uses the same browser session Home Depot already accepts.

## Automatic Active Listings Sync

1. Start AutoZS and select the correct eBay store.
2. Press Sync Now in the dashboard.
3. Keep the generated Seller Hub Reports tab open while eBay prepares the report.

The extension requests a fresh All active listings report, downloads it when eBay marks it complete, and the local API imports it from `~/Downloads/AutoZS`. Imported files move into `~/Downloads/AutoZS/processed`; failed files move into `~/Downloads/AutoZS/failed` and the sync run changes to Needs review.
