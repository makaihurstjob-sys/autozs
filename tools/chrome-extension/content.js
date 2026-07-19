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
  const progressLogoUrl = (() => {
    try {
      return typeof chrome !== "undefined" && chrome.runtime?.getURL
        ? chrome.runtime.getURL("assets/autozs-logo.png")
        : "";
    } catch {
      return "";
    }
  })();
  let autoProgressHost = null;
  let autoProgressPercent = 0;
  const ensureAutoProgressOverlay = () => {
    if (autoProgressHost?.shadowRoot) return autoProgressHost;
    const mount = document.documentElement || document.body;
    if (!mount || typeof document.createElement !== "function") return null;
    const progressHost = document.createElement("div");
    progressHost.id = "autozs-source-import-progress-host";
    progressHost.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:auto;";
    if (typeof progressHost.attachShadow !== "function") return null;
    const progressShadow = progressHost.attachShadow({ mode: "open" });
    progressShadow.innerHTML = `
      <style>
        :host {
          --az-bg: #111a15;
          --az-line: #2b352f;
          --az-ink: #edf4ef;
          --az-muted: #9aa89f;
          --az-accent: #4bb7a6;
        }
        .progress-overlay {
          align-items: center;
          background: rgba(10, 14, 12, .74);
          backdrop-filter: blur(3px);
          color: var(--az-ink);
          display: flex;
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          inset: 0;
          justify-content: center;
          pointer-events: auto;
          position: absolute;
        }
        .progress-card {
          align-items: center;
          background: var(--az-bg);
          border: 1px solid var(--az-line);
          border-radius: 8px;
          box-shadow: 0 24px 70px rgba(0,0,0,.38);
          display: grid;
          gap: 14px;
          justify-items: center;
          padding: 28px;
          width: min(410px, calc(100vw - 48px));
        }
        .logo { height: 52px; object-fit: contain; width: 52px; }
        .progress-title { font-size: 28px; font-weight: 850; line-height: 1.1; text-align: center; }
        .progress-label { color: var(--az-muted); font-size: 13px; line-height: 1.35; min-height: 18px; text-align: center; }
        .progress-track { background: #263631; border-radius: 999px; height: 10px; overflow: hidden; width: 100%; }
        .progress-fill { background: var(--az-accent); height: 100%; transition: width .22s ease; width: 0%; }
        .progress-percent { color: var(--az-ink); font-size: 13px; font-weight: 800; }
        .progress-note { color: var(--az-muted); font-size: 11px; text-align: center; }
        :host([data-state="error"]) .progress-fill { background: #ff6b6b; }
        :host([data-state="complete"]) .progress-fill { background: #56d88a; }
      </style>
      <div class="progress-overlay" role="status" aria-live="polite">
        <div class="progress-card">
          ${progressLogoUrl ? `<img class="logo" src="${progressLogoUrl}" alt="AutoZS" draggable="false" />` : ""}
          <div class="progress-title">AutoZS is working</div>
          <div id="progress-label" class="progress-label">Preparing automatic product import...</div>
          <div class="progress-track" aria-hidden="true"><div id="progress-fill" class="progress-fill"></div></div>
          <div id="progress-percent" class="progress-percent">0%</div>
          <div class="progress-note">Keep this tab open until AutoZS finishes.</div>
        </div>
      </div>
    `;
    if (typeof mount.appendChild === "function") mount.appendChild(progressHost);
    else if (typeof mount.append === "function") mount.append(progressHost);
    else return null;
    autoProgressHost = progressHost;
    return autoProgressHost;
  };
  const setAutoProgress = (text, percent = autoProgressPercent, state = "working") => {
    const progressHost = ensureAutoProgressOverlay();
    if (!progressHost?.shadowRoot) return;
    autoProgressPercent = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
    progressHost.setAttribute?.("data-state", state);
    const progressLabel = progressHost.shadowRoot.querySelector("#progress-label");
    const progressFill = progressHost.shadowRoot.querySelector("#progress-fill");
    const progressPercent = progressHost.shadowRoot.querySelector("#progress-percent");
    if (progressLabel) progressLabel.textContent = text;
    if (progressFill) progressFill.style.width = `${autoProgressPercent}%`;
    if (progressPercent) progressPercent.textContent = `${autoProgressPercent}%`;
  };
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
  const captureWhenReady = async (onProgress = () => {}) => {
    let latestPayload = null;
    let latestError = null;
    for (let attempt = 1; attempt <= 12; attempt += 1) {
      try {
        latestPayload = captureSourceProductFromPage();
        latestError = null;
      } catch (error) {
        latestError = error;
        if (!/Home Depot showed an error page/i.test(error.message || String(error)) || attempt === 12) throw error;
        onProgress(Math.min(44, 22 + attempt * 2), `Home Depot is still settling; checking again (${attempt}/12)...`);
        setStatus(`Home Depot is still settling; checking again (${attempt}/12)...`);
        await sleep(700);
        continue;
      }
      if (isCaptureReady(latestPayload)) {
        onProgress(48, "Product data captured.");
        return latestPayload;
      }
      const readiness = payloadReadiness(latestPayload);
      onProgress(Math.min(44, 22 + attempt * 2), `Waiting for Home Depot product data (${attempt}/12)...`);
      setStatus(
        `Waiting for page data... title ${readiness.title ? "yes" : "no"}, price ${
          readiness.price ? "yes" : "no"
        }, images ${readiness.images ? "yes" : "no"} (${attempt}/12)`
      );
      await sleep(700);
    }
    if (latestError) throw latestError;
    return latestPayload || captureSourceProductFromPage();
  };

  const captureAndImport = async (mode = "manual") => {
    const refreshContext = typeof sourceRefreshContextFromLocation === "function" ? sourceRefreshContextFromLocation() : null;
    const automatic = mode === "auto";
    const closeCompletedRefreshTab = () => {
      if (!automatic || !refreshContext) return;
      setTimeout(() => {
        chrome.runtime.sendMessage({
          type: "autozs-close-source-refresh-tab",
          jobId: refreshContext.jobId,
        }).catch(() => {});
      }, 1500);
    };
    const progress = (percent, text, state = "working") => {
      if (automatic) setAutoProgress(text, percent, state);
    };
    button.disabled = true;
    button.textContent = mode === "auto" ? "Importing..." : "Checking...";
    setStatus(mode === "auto" ? "Auto-import requested. Checking local app..." : "Checking local app...");
    progress(6, refreshContext ? "Starting scheduled source-price import..." : "Starting automatic product import...");
    try {
      await checkLocalApi();
      progress(16, "Connected to AutoZS.");
      button.textContent = "Importing...";
      setStatus("Capturing visible product data...");
      progress(22, "Capturing visible product data...");
      const payload = await captureWhenReady((percent, text) => progress(percent, text));
      if (payload.detected_shipping !== null && payload.detected_shipping !== undefined) payload.source_shipping = payload.detected_shipping;
      delete payload.detected_shipping;
      if (refreshContext) payload.refresh_job_id = refreshContext.jobId;
      progress(58, refreshContext ? "Importing the latest source price into AutoZS..." : "Importing the product into AutoZS...");
      const product = await importCapturedProduct(payload);
      progress(78, refreshContext ? "Source price saved." : "Product saved. Preparing images...");
      setStatus(refreshContext ? "Price refresh saved." : "Import saved. Downloading product images...");
      let imageStatus = "no image URLs found";
      if (!refreshContext && product.images && product.images.length) {
        try {
          progress(84, "Downloading product images...");
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
        try {
          await chrome.runtime.sendMessage({ type: "autozs-source-refresh-cooldown" });
        } catch {}
        setStatus(`Refreshed ${product.sku}. The background worker will continue after the Home Depot cooldown.`);
      }
      progress(100, refreshContext ? "Source price imported. AutoZS will continue the schedule." : `Imported ${product.sku} into AutoZS.`, "complete");
      closeCompletedRefreshTab();
    } catch (error) {
      setStatus(`Import failed: ${error.message}`);
      button.textContent = "Import failed";
      progress(autoProgressPercent || 10, `Import needs attention: ${error.message || String(error)}`, "error");
      if (refreshContext) {
        const isHomeDepotError = /Home Depot showed an error page/i.test(error.message || String(error));
        const retryAlreadyAttempted = new URLSearchParams(location.search).get("autozs_error_retry") === "1";
        if (isHomeDepotError && !retryAlreadyAttempted) {
          try {
            const cleanup = await chrome.runtime.sendMessage({ type: "autozs-home-depot-batch-cleanup" });
            if (cleanup?.ok) {
              const retryUrl = new URL(location.href);
              retryUrl.searchParams.set("autozs_error_retry", "1");
              setStatus(`Home Depot error detected. Cleared ${Number(cleanup.cleared || 0)} Home Depot cookie(s), cache, and site data; retrying once...`);
              progress(12, "Home Depot was blocked. Site data cleared; retrying once...");
              setTimeout(() => location.replace(retryUrl.href), 1200);
              return;
            }
          } catch {}
        }
        try {
          const failedJob = await failSourceRefreshJob(refreshContext.jobId, error.message || String(error));
          if (failedJob?.status === "cancelled") {
            setStatus(failedJob.message || "This refresh was superseded by a newer successful capture.");
            progress(100, "A newer source-price refresh already completed this product.", "complete");
            closeCompletedRefreshTab();
          } else {
            setStatus(`Refresh paused after an error. The worker will retry the queue after its cooldown.`);
          }
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
    setAutoProgress("Waiting for the scheduled product page to settle...", 2);
    setTimeout(() => captureAndImport("auto"), 1800);
  }

  window.addEventListener("beforeunload", () => {
    observer.disconnect();
  });
})();
