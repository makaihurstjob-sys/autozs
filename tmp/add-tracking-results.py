from pathlib import Path
p=Path('tools/chrome-extension/background.js');s=p.read_text(encoding='utf-8');mark='async function openNextSupplierTrackingCheck()';helper='''async function recordSupplierTrackingResult(urlValue, outcome) {
  const url = new URL(urlValue);
  if (url.hostname !== "www.homedepot.com") return;
  const redirect = new URL(url.searchParams.get("redirect") || "/", url.origin);
  const orderId = url.searchParams.get("orderNumber") || url.searchParams.get("orderId") || redirect.searchParams.get("orderId");
  if (!/^[A-Z0-9-]{6,128}$/i.test(orderId || "")) return;
  const key = `autozsTrackingResults:${orderId}`;
  const stored = await chrome.storage.local.get(key);
  const events = Array.isArray(stored[key]) ? stored[key] : [];
  events.push({ outcome, checkedAt: new Date().toISOString(), page: url.pathname });
  await chrome.storage.local.set({ [key]: events.slice(-20) });
}

''';s=s.replace(mark,helper+mark,1);s=s.replace('  if (signInTabs.length) {','  if (signInTabs.length) {\n    await recordSupplierTrackingResult(signInTabs[0].url, "sign_in_required");',1);s=s.replace('    await chrome.tabs.remove(tab.id);\n  }\n  const stored = await chrome.storage.local.get([SUPPLIER_TRACKING', '    await recordSupplierTrackingResult(tab.url, "page_timeout");\n    await chrome.tabs.remove(tab.id);\n  }\n  const stored = await chrome.storage.local.get([SUPPLIER_TRACKING',1)
s=s.replace('        sendResponse({ ok: true, status: order.status });\n        if (isSupplierTrackingRunnerUrl', '        await recordSupplierTrackingResult(sender.tab.url, "tracking_captured");\n        sendResponse({ ok: true, status: order.status });\n        if (isSupplierTrackingRunnerUrl',1)
s=s.replace('''    sendResponse({ ok: true });
    chrome.tabs.remove(sender.tab.id).catch(() => {});
    return false;
  }
  if (message?.type === "autozs-supplier-tracking-blocked")''','''    recordSupplierTrackingResult(sender.tab.url, message.orderVerified === true ? "verified_no_tracking" : "page_unverified")
      .then(() => chrome.tabs.remove(sender.tab.id))
      .then(() => sendResponse({ ok: true }))
      .catch(error => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "autozs-supplier-tracking-blocked")''',1)
s=s.replace('''    chrome.storage.local.set({ [SUPPLIER_TRACKING_BLOCKED_UNTIL_KEY]: Date.now() + SUPPLIER_TRACKING_ERROR_COOLDOWN_MS })
      .then(() => sender.tab?.id''','''    recordSupplierTrackingResult(sender.tab.url, "page_failed")
      .then(() => chrome.storage.local.set({ [SUPPLIER_TRACKING_BLOCKED_UNTIL_KEY]: Date.now() + SUPPLIER_TRACKING_ERROR_COOLDOWN_MS }))
      .then(() => sender.tab?.id''',1);p.write_text(s,encoding='utf-8')
p=Path('tools/chrome-extension/home-depot-checkout.js');s=p.read_text(encoding='utf-8');helper='''function autozsTrackingOrderVerified(urlValue, bodyText) {
  const url = new URL(urlValue);
  const orderId = url.searchParams.get("orderNumber") || url.searchParams.get("orderId");
  return url.hostname === "www.homedepot.com" && url.pathname === "/myaccount/order-details"
    && /^[A-Z0-9-]{6,128}$/i.test(orderId || "")
    && new RegExp(`ORDER\\\\s*#\\\\s*${orderId}\\\\b`, "i").test(bodyText || "")
    && !/pardon our dust|page you are looking for no longer exists/i.test(bodyText || "");
}

''';s=s.replace('async function autozsObserveHomeDepotTrackingBounded()',helper+'async function autozsObserveHomeDepotTrackingBounded()',1);s=s.replace('{ type: "autozs-supplier-tracking-waiting" }','{ type: "autozs-supplier-tracking-waiting", orderVerified: autozsTrackingOrderVerified(location.href, document.body?.innerText) }');p.write_text(s,encoding='utf-8')
p=Path('tools/chrome-extension/tracking-poll.test.js');s=p.read_text().replace('const c={Date,URL,','const c={recordSupplierTrackingResult:async()=>{},Date,URL,').replace('const c={URL,canRun','const c={recordSupplierTrackingResult:async()=>{},URL,canRun');p.write_text(s)
