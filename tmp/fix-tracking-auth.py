from pathlib import Path
p=Path('tools/chrome-extension/background.js');s=p.read_text(encoding='utf-8');needle='''  const tabs = await chrome.tabs.query({ url: "https://www.homedepot.com/*" });
  for (const tab of tabs.filter(tab => isSupplierTrackingRunnerUrl(tab.url))) {''';repl='''  const tabs = await chrome.tabs.query({ url: "https://www.homedepot.com/*" });
  // Authentication redirects are no longer runner URLs. Keep one visible handoff
  // instead of opening a fresh login tab for every pending supplier order.
  const signInTabs = tabs.filter(tab => {
    try {
      const url = new URL(tab.url);
      const redirect = new URL(url.searchParams.get("redirect") || "/", url.origin);
      return url.hostname === "www.homedepot.com" && url.pathname === "/auth/view/signin"
        && redirect.pathname === "/myaccount/purchase-history"
        && (url.searchParams.get("autozs_tracking_poll") === "1"
          || redirect.searchParams.get("autozs_tracking_poll") === "1");
    } catch { return false; }
  });
  if (signInTabs.length) {
    for (const duplicate of signInTabs.slice(1)) await chrome.tabs.remove(duplicate.id);
    return;
  }
  for (const tab of tabs.filter(tab => isSupplierTrackingRunnerUrl(tab.url))) {''';assert needle in s;s=s.replace(needle,repl,1);p.write_text(s,encoding='utf-8')
