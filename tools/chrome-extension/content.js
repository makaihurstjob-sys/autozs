(async () => {
  if (window.__ebayAutomationImportButton) return;
  window.__ebayAutomationImportButton = true;

  const waitForBody = () =>
    new Promise((resolve) => {
      if (document.body) {
        resolve();
        return;
      }
      const timer = setInterval(() => {
        if (document.body) {
          clearInterval(timer);
          resolve();
        }
      }, 100);
    });

  await waitForBody();

  const host = document.createElement("div");
  host.id = "ebay-automation-import-host";
  host.style.cssText = "position:relative;z-index:2147483000;width:100%;";
  const shadow = host.attachShadow({ mode: "open" });
  const importArtworkUrl = (() => {
    try {
      return typeof chrome !== "undefined" && chrome.runtime?.getURL
        ? chrome.runtime.getURL("assets/import-to-autozs.png")
        : "assets/import-to-autozs.png";
    } catch {
      return "assets/import-to-autozs.png";
    }
  })();
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      .import-action {
        display: block;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        margin: 0;
        position: relative;
        height: 61px;
        width: 100%;
      }
      .import-artwork {
        display: block;
        height: 61px;
        pointer-events: none;
        user-select: none;
        width: 122px;
      }
      button {
        background: transparent;
        border: 0;
        border-radius: 20px 0 0 20px;
        color: transparent;
        cursor: pointer;
        font-size: 0;
        height: 61px;
        left: 0;
        margin: 0;
        padding: 0;
        position: absolute;
        top: 0;
        width: 61px;
      }
      button:hover { background: rgba(255, 255, 255, .1); }
      button:focus-visible { outline: 3px solid #195f56; outline-offset: 3px; }
      button:disabled { background: rgba(0, 0, 0, .14); cursor: wait; }
      .status {
        height: 1px;
        overflow: hidden;
        position: absolute;
        width: 1px;
        clip: rect(0 0 0 0);
        clip-path: inset(50%);
      }
      @media (max-width: 640px) {
        .import-action, .import-artwork { max-width: 122px; width: 100%; }
        .import-artwork { object-fit: contain; object-position: left center; }
        button { width: 50%; }
      }
    </style>
    <div class="import-action">
      <img class="import-artwork" src="${importArtworkUrl}" alt="" draggable="false">
      <button type="button" aria-label="Import this product to AutoZS" title="Import to AutoZS">Import to AutoZS</button>
      <span class="status" aria-live="polite"></span>
    </div>
  `;

  const findPurchasePanel = () => {
    const title = document.querySelector("h1");
    const titleActions = title
      ?.closest('[data-component^="product-details:ProductDetails:"]')
      ?.querySelector('[data-testid="sharabelt-product-details"]');
    if (titleActions) {
      return { element: titleActions, placement: "title-actions" };
    }

    let summaryColumn = title;
    while (summaryColumn?.parentElement && !summaryColumn.querySelector?.('[data-component^="price:Price"]')) {
      summaryColumn = summaryColumn.parentElement;
    }
    const primaryPrice = summaryColumn?.querySelector?.('[data-component^="price:Price"]');
    if (primaryPrice?.parentElement) {
      return { element: primaryPrice.parentElement, placement: "price-overlay" };
    }

    const panel = [
      '[data-testid*="buybox" i]',
      '[data-testid*="buy-box" i]',
      '[data-testid*="purchase" i]',
      '[data-component*="buybox" i]',
      '[class*="buybox" i]',
      '[class*="buy-box" i]',
    ].map((selector) => document.querySelector(selector)).find(Boolean);
    if (panel) return { element: panel, placement: "append" };

    const priceAnchor = [
      '[data-testid*="price" i]',
      '[data-component*="price" i]',
      '[class*="price" i]',
    ].map((selector) => document.querySelector(selector)).find((element) => /\$\s*\d/.test(element?.textContent || ""));
    return priceAnchor ? { element: priceAnchor, placement: "afterend" } : null;
  };

  const hostIsInPanel = (target) => host.parentNode === target.element;

  const insertHost = () => {
    if (!document.body) return false;
    const target = findPurchasePanel();
    if (!target) return false;
    if (!hostIsInPanel(target)) {
      if (target.placement === "title-actions") {
        target.element.style.display = "flex";
        target.element.style.alignItems = "center";
        target.element.style.gap = "8px";
        host.style.cssText =
          "position:relative;z-index:2147483000;width:122px;height:61px;flex:0 0 122px;";
        target.element.prepend(host);
      } else if (target.placement === "price-overlay") {
        target.element.style.display = "grid";
        target.element.style.gridTemplateColumns = "minmax(0, 1fr) 122px";
        target.element.style.alignItems = "end";
        target.element.style.columnGap = "16px";
        host.style.cssText =
          "position:relative;z-index:2147483000;width:122px;grid-column:2;grid-row:1;";
        target.element.append(host);
      } else if (target.placement === "afterend") {
        host.style.cssText = "position:relative;z-index:2147483000;width:100%;";
        target.element.insertAdjacentElement("afterend", host);
      } else {
        host.style.cssText = "position:relative;z-index:2147483000;width:100%;";
        target.element.append(host);
      }
    }
    return true;
  };

  insertHost();
  let tries = 0;
  const retryTimer = setInterval(() => {
    tries += 1;
    if (insertHost() || tries > 30) {
      clearInterval(retryTimer);
      return;
    }
  }, 500);

  const observer = new MutationObserver(() => {
    if (!document.getElementById(host.id)) insertHost();
  });
  observer.observe(document.body, { childList: true });

  const button = shadow.querySelector("button");
  const status = shadow.querySelector(".status");
  const setStatus = (text) => {
    status.textContent = text;
    status.title = text;
  };
  const readImageDownloadStatus = (result) =>
    typeof imageDownloadStatus === "function" ? imageDownloadStatus(result) : `${result.downloaded}/${result.attempted} images downloaded`;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const payloadReadiness = (payload) => ({
    title: Boolean(payload?.title && String(payload.title).trim() && !/^home\s*depot$/i.test(String(payload.title).trim())),
    price: payload?.source_price !== null && payload?.source_price !== undefined,
    images: Boolean(payload?.image_urls && String(payload.image_urls).split("\n").filter(Boolean).length),
  });
  const isCaptureReady = (payload) => {
    const readiness = payloadReadiness(payload);
    return readiness.title && readiness.price && readiness.images;
  };
  const captureWhenReady = async () => {
    let latestPayload = null;
    for (let attempt = 1; attempt <= 12; attempt += 1) {
      latestPayload = captureSourceProductFromPage();
      if (isCaptureReady(latestPayload)) return latestPayload;
      const readiness = payloadReadiness(latestPayload);
      setStatus(
        `Waiting for page data... title ${readiness.title ? "yes" : "no"}, price ${
          readiness.price ? "yes" : "no"
        }, images ${readiness.images ? "yes" : "no"} (${attempt}/12)`
      );
      await sleep(700);
    }
    return latestPayload || captureSourceProductFromPage();
  };

  const captureAndImport = async (mode = "manual") => {
    const refreshContext = typeof sourceRefreshContextFromLocation === "function" ? sourceRefreshContextFromLocation() : null;
    button.disabled = true;
    button.textContent = mode === "auto" ? "Importing..." : "Checking...";
    setStatus(mode === "auto" ? "Auto-import requested. Checking local app..." : "Checking local app...");
    try {
      await checkLocalApi();
      button.textContent = "Importing...";
      setStatus("Capturing visible product data...");
      const payload = await captureWhenReady();
      if (payload.detected_shipping !== null && payload.detected_shipping !== undefined) payload.source_shipping = payload.detected_shipping;
      delete payload.detected_shipping;
      if (refreshContext) payload.refresh_job_id = refreshContext.jobId;
      const product = await importCapturedProduct(payload);
      setStatus(refreshContext ? "Price refresh saved." : "Import saved. Downloading product images...");
      let imageStatus = "no image URLs found";
      if (!refreshContext && product.images && product.images.length) {
        try {
          const imageResult = await downloadProductImages(product.id);
          imageStatus = readImageDownloadStatus(imageResult);
        } catch (imageError) {
          imageStatus = `image download failed: ${imageError.message}`;
        }
      }
      setStatus(
        `Imported ${product.sku}; shipping ${
          payload.source_shipping === undefined ? "unknown" : payload.source_shipping === 0 ? "free" : `$${Number(payload.source_shipping).toFixed(2)}`
        }; ${payload.subscription_discount_percent ? `${payload.subscription_discount_percent}% subscription discount; ` : ""}${
          payload.image_urls ? payload.image_urls.split("\\n").length : 0
        } image URL(s); ${imageStatus}.`
      );
      button.textContent = "Imported";
      if (refreshContext) {
        setStatus(`Refreshed ${product.sku}. Cooling down before the next product...`);
        setTimeout(async () => {
          try {
            const nextJob = await claimNextSourceRefreshJob(refreshContext.batchKey);
            if (nextJob?.runner_url) location.replace(nextJob.runner_url);
            else {
              let cleanupMessage = "Home Depot batch state cleaned.";
              try {
                const cleanup = await chrome.runtime.sendMessage({ type: "autozs-home-depot-batch-cleanup" });
                if (!cleanup?.ok) cleanupMessage = "Batch cleanup will retry with the next worker run.";
              } catch {
                cleanupMessage = "Batch cleanup will retry with the next worker run.";
              }
              setStatus(`Refresh batch complete. Last product: ${product.sku}. ${cleanupMessage}`);
            }
          } catch (nextError) {
            setStatus(`Refreshed ${product.sku}. Next product will resume on the worker poll.`);
          }
        }, 45 * 1000);
      }
    } catch (error) {
      setStatus(`Import failed: ${error.message}`);
      button.textContent = "Import failed";
      if (refreshContext) {
        try {
          await failSourceRefreshJob(refreshContext.jobId, error.message || String(error));
          setStatus(`Refresh paused after an error. The worker will retry the queue after its cooldown.`);
        } catch {}
      }
    } finally {
      setTimeout(() => {
        button.disabled = false;
        button.textContent = "Import to Website";
      }, 1800);
    }
  };

  button.addEventListener("click", () => captureAndImport("manual"));

  const autoImportRequested = new URLSearchParams(location.search).get("ea_auto_import") === "1";
  if (autoImportRequested && !window.__ebayAutomationAutoImportStarted) {
    window.__ebayAutomationAutoImportStarted = true;
    setStatus("Auto-import will start after the page settles...");
    setTimeout(() => captureAndImport("auto"), 1800);
  }

  window.addEventListener("beforeunload", () => {
    observer.disconnect();
  });
})();
