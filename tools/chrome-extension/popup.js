function setStatus(text) {
  document.getElementById("status").textContent = text;
}

function setConnectionState(state) {
  const status = document.getElementById("connection-status");
  const label = document.getElementById("connection-label");
  if (status) status.dataset.state = state;
  if (label) label.textContent = state === "live" ? "Live" : state === "offline" ? "Offline" : "Syncing";
}

function applyTheme(theme) {
  document.body.dataset.theme = theme === "dark" || theme === "light" ? theme : "system";
}

function readImageDownloadStatus(result) {
  return typeof imageDownloadStatus === "function" ? imageDownloadStatus(result) : `${result.downloaded}/${result.attempted} images downloaded`;
}

async function syncTheme() {
  applyTheme(await readAppTheme());
}

function autozsProductIdFromUrl(url) {
  try {
    const parsed = new URL(url || "");
    const hashMatch = parsed.hash.match(/(?:^#|[&])(?:autozs_product_id|autozs_popup_product_id)=([^&]+)/);
    return parsed.searchParams.get("autozs_product_id") || (hashMatch ? decodeURIComponent(hashMatch[1]) : "");
  } catch {
    return "";
  }
}

function setEbayProductIdDisplay(productId) {
  const display = document.getElementById("ebay-product-id");
  if (!display) return;
  const value = String(productId || "").trim();
  if (display.dataset) display.dataset.productId = value;
  display.textContent = value || "—";
}

async function syncEbayProductIdDisplay() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const productId = autozsProductIdFromUrl(tab?.url);
  setEbayProductIdDisplay(productId);
  return productId;
}

async function checkApi(showError = false) {
  try {
    const body = await checkLocalApi();
    await syncTheme();
    const online = body.status === "ok";
    setConnectionState(online ? "live" : "offline");
    if (!online && showError) setStatus(`Unexpected API response: ${JSON.stringify(body)}`);
    return online;
  } catch (error) {
    setConnectionState("offline");
    if (showError) setStatus(`Local API is offline or blocked: ${error.message}`);
    return false;
  }
}

async function captureCurrentTab() {
  setStatus("Checking local API...");
  if (!(await checkApi(true))) return;
  setStatus("Capturing current tab...");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatus("No active tab found.");
    return;
  }

  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: captureSourceProductFromPage,
    });

    const payload = { ...result };
    if (result.detected_shipping !== null && result.detected_shipping !== undefined) payload.source_shipping = result.detected_shipping;
    delete payload.detected_shipping;

    const product = await importCapturedProduct(payload);
    setStatus(`Imported ${product.sku}. Downloading product images...`);
    let imageStatus = "no image URLs found";
    if (product.images && product.images.length) {
      try {
        const imageResult = await downloadProductImages(product.id);
        imageStatus = readImageDownloadStatus(imageResult);
      } catch (imageError) {
        imageStatus = `image download failed: ${imageError.message}`;
      }
    }
    setStatus(
      `Imported ${product.sku}\nSource price: ${payload.source_price ?? "not found"}\nShipping: ${
        payload.source_shipping === undefined ? "unknown" : payload.source_shipping === 0 ? "free" : `$${Number(payload.source_shipping).toFixed(2)}`
      }\nSubscription discount: ${payload.subscription_discount_percent ? `${payload.subscription_discount_percent}%` : "none detected"}\nImages: ${
        payload.image_urls ? payload.image_urls.split("\n").length : 0
      }\nDownloaded: ${imageStatus}`
    );
  } catch (error) {
    const hint = error.message === "Failed to fetch" ? "\n\nHint: make sure the local API is running and reload this unpacked extension after updates." : "";
    setStatus(`Capture failed: ${error.message}${hint}`);
  }
}

async function showEbayAssistant() {
  setStatus("Checking local API...");
  if (!(await checkApi(true))) return;

  const productId = Number(await syncEbayProductIdDisplay());
  if (!productId) {
    setStatus("Open an AutoZS eBay draft from the dashboard first so its product ID can be detected.");
    return;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https:\/\/([^/]+\.)?ebay\.com\//i.test(tab.url || "")) {
    setStatus("Open an eBay listing draft tab first, then retry.");
    return;
  }

  try {
    const [{ result: toggleResult }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const currentBuild = "2026-06-30-html-source";
        const host = document.getElementById("autozs-ebay-fill-assistant");
        if (!host) return { wasVisible: false };
        if (host.getAttribute("data-autozs-build") !== currentBuild) {
          host.remove();
          window.__autozsEbayFillAssistant = false;
          return { wasVisible: false, replacedStale: true };
        }
        host.remove();
        window.__autozsEbayFillAssistant = false;
        return { wasVisible: true };
      },
    });
    if (toggleResult?.wasVisible) {
      document.getElementById("show-ebay-assistant").textContent = "Show eBay Assistant";
      setStatus("AutoZS Listing Assistant hidden.");
      return;
    }

    const accountStatus = await refreshEbayBrowserAccountFromActiveTab("manual");
    if (!accountStatus.can_list) {
      setStatus(accountStatus.message);
      return;
    }
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      args: [String(productId)],
      func: (selectedProductId) => {
        try {
          localStorage.setItem("autozs_last_product_id", selectedProductId);
        } catch {}
        if (!location.hash.includes("autozs_product_id")) {
          const separator = location.hash ? "&" : "#";
          history.replaceState(null, "", `${location.pathname}${location.search}${location.hash}${separator}autozs_fill=1&autozs_product_id=${encodeURIComponent(selectedProductId)}`);
        }
      },
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["capture.js", "ebay-fill.js"],
    });
    document.getElementById("show-ebay-assistant").textContent = "Hide eBay Assistant";
    setStatus(`AutoZS Listing Assistant opened for product ${productId}. Use Fill Listing to create and save an eBay draft for review.`);
  } catch (error) {
    setStatus(`Could not open eBay assistant: ${error.message}`);
  }
}

async function refreshEbayBrowserAccountFromActiveTab(accountKey = "manual") {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https:\/\/([^/]+\.)?ebay\.(com|co\.uk|ca|com\.au)\//i.test(tab.url || "")) {
    throw new Error("Open eBay in the active Chrome tab so AutoZS can confirm the signed-in username.");
  }
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: detectEbaySignedInUsernameFromPage,
  });
  if (!result) {
    const query = accountKey ? `?account_key=${encodeURIComponent(accountKey)}` : "";
    const fallbackResponse = await fetch(`${API}/ebay/browser-account${query}`, { cache: "no-store" });
    if (!fallbackResponse.ok) throw new Error(await fallbackResponse.text());
    return fallbackResponse.json();
  }
  const response = await fetch(`${API}/ebay/browser-account`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      detected_username: result || null,
      url: tab.url || "",
      marketplace: "EBAY_US",
      source: "chrome-extension-popup",
      account_key: accountKey || "manual",
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

applyTheme(fallbackTheme());
syncTheme();
checkApi();
syncEbayProductIdDisplay().catch(() => setEbayProductIdDisplay(""));
window.matchMedia?.("(prefers-color-scheme: dark)")?.addEventListener?.("change", () => {
  syncTheme();
});
document.getElementById("capture").addEventListener("click", captureCurrentTab);
document.getElementById("show-ebay-assistant").addEventListener("click", showEbayAssistant);
document.getElementById("open-dashboard").addEventListener("click", () => {
  chrome.tabs.create({ url: DASHBOARD });
});
