(() => {
  if (window.__autozsDashboardBridgeInstalled) return;
  window.__autozsDashboardBridgeInstalled = true;

  const requestedWorkerMode = new URLSearchParams(location.search).get("autozs_worker_mode");
  if (["operations", "capture", "viewer"].includes(requestedWorkerMode)) {
    try {
      chrome.runtime.sendMessage({ type: "autozs-configure-worker-mode", mode: requestedWorkerMode })?.catch?.(() => {});
    } catch {}
  }

  window.addEventListener("message", (event) => {
    if (
      event.source !== window ||
      event.data?.source !== "autozs-dashboard" ||
      event.data?.type !== "autozs-start-product-capture"
    ) return;
    try {
      const request = chrome.runtime.sendMessage({ type: "autozs-start-product-capture" });
      request?.catch?.(() => {});
    } catch {
      // An extension reload invalidates scripts already injected into this tab.
      // The background alarm remains a fallback after the dashboard refreshes.
    }
  });
})();
