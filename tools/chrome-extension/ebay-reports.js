(async () => {
  if (window.__autozsEbayReportRunnerStarted) return;

  function syncContext() {
    const search = String(location.search || "").replace(/^\?/, "");
    const hash = String(location.hash || "").replace(/^#/, "");
    const params = new URLSearchParams([search, hash].filter(Boolean).join("&"));
    const runId = Number(params.get("autozs_sync_run"));
    if (!runId) return null;
    return {
      runId,
      accountKey: params.get("autozs_account_key") || "manual",
      reportType: params.get("autozs_report_type") || "active_listings",
    };
  }

  const context = syncContext();
  const onActiveListings = /^\/sh\/lst\/active/i.test(location.pathname || "");
  const onReportDownloads = /^\/sh\/reports\/downloads/i.test(location.pathname || "");
  if (!context || (!onActiveListings && !onReportDownloads)) return;
  window.__autozsEbayReportRunnerStarted = true;

  const REPORT_CREATE_TIMEOUT_MS = 3 * 60 * 1000;
  const REPORT_COMPLETE_TIMEOUT_MS = 3 * 60 * 1000;
  const IMPORT_COMPLETE_TIMEOUT_MS = 60 * 1000;

  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (element) => Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
  const logoUrl = chrome.runtime?.getURL ? chrome.runtime.getURL("assets/autozs-logo.png") : "";

  async function waitFor(find, timeout = 30000, interval = 300) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const value = await find();
      if (value) return value;
      await new Promise((resolve) => setTimeout(resolve, interval));
    }
    throw new Error("eBay did not finish the expected report step in time.");
  }

  async function patchRun(payload) {
    const response = await fetch(`${API}/ebay/sync-runs/${context.runId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }

  async function readRun() {
    const response = await fetch(`${API}/ebay/sync-runs/${context.runId}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }

  async function prepareReportDownloadContext() {
    const response = await chrome.runtime.sendMessage({ type: "autozs-ebay-report-sync-context", ...context });
    if (!response?.ok) throw new Error(response?.error || "AutoZS could not prepare the report download.");
  }

  async function closeReportRunnerTab() {
    try {
      await chrome.runtime.sendMessage({ type: "autozs-close-report-runner-tab", runId: context.runId });
    } catch {
      window.close();
    }
  }

  async function waitForImportCompletionAndClose() {
    setRunnerStatus("AutoZS is importing and reconciling the report...", "working", 90);
    const run = await waitFor(async () => {
      const latest = await readRun();
      if (latest.status === "completed") return latest;
      if (["failed", "needs_review"].includes(latest.status)) {
        throw new Error(latest.message || `AutoZS sync ${latest.status}.`);
      }
      return null;
    }, IMPORT_COMPLETE_TIMEOUT_MS, 1000);
    setRunnerStatus(run.message || "AutoZS import complete. Closing this report tab.", "complete", 100);
    setTimeout(closeReportRunnerTab, 800);
    return run;
  }

  function ensureRunnerProgressOverlay() {
    let host = document.getElementById("autozs-report-progress-host");
    if (host?.shadowRoot) return host;
    host = document.createElement("div");
    host.id = "autozs-report-progress-host";
    host.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:auto";
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
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
          width: min(390px, calc(100vw - 48px));
        }
        .logo {
          height: 52px;
          object-fit: contain;
          width: 52px;
        }
        .progress-title {
          font-size: 28px;
          font-weight: 850;
          letter-spacing: 0;
          line-height: 1.1;
          text-align: center;
        }
        .progress-label {
          color: var(--az-muted);
          font-size: 13px;
          min-height: 18px;
          text-align: center;
        }
        .progress-track {
          background: #263631;
          border-radius: 999px;
          height: 10px;
          overflow: hidden;
          width: 100%;
        }
        .progress-fill {
          background: var(--az-accent);
          height: 100%;
          transition: width .22s ease;
          width: 0%;
        }
        .progress-percent {
          color: var(--az-ink);
          font-size: 13px;
          font-weight: 800;
        }
        :host([data-state="error"]) .progress-fill { background: #ff6b6b; }
      </style>
      <div class="progress-overlay" role="status" aria-live="polite">
        <div class="progress-card">
          ${logoUrl ? `<img class="logo" src="${logoUrl}" alt="AutoZS" draggable="false" />` : ""}
          <div class="progress-title">Auto-ZS in progress</div>
          <div id="progress-label" class="progress-label">Preparing eBay sync...</div>
          <div class="progress-track" aria-hidden="true"><div id="progress-fill" class="progress-fill"></div></div>
          <div id="progress-percent" class="progress-percent">0%</div>
        </div>
      </div>
    `;
    document.documentElement.appendChild(host);
    return host;
  }

  function setRunnerStatus(text, state = "working", percent = 0) {
    const host = ensureRunnerProgressOverlay();
    const shadow = host.shadowRoot;
    const safePercent = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
    host.dataset.state = state;
    shadow.querySelector("#progress-label").textContent = text;
    shadow.querySelector("#progress-fill").style.width = `${safePercent}%`;
    shadow.querySelector("#progress-percent").textContent = `${safePercent}%`;
  }

  function activeListingViewRows() {
    return Array.from(document.querySelectorAll("tr,[role='row']")).map((row) => {
      const titleCell = row.querySelector(".shui-dt-column__title");
      const viewsCell = row.querySelector(".shui-dt-column__visitCount");
      const listingId = clean(titleCell?.innerText || titleCell?.textContent).match(/\b\d{12}\b/)?.[0] || "";
      const viewsText = clean(viewsCell?.innerText || viewsCell?.textContent);
      const viewsMatch = viewsText.match(/\bViews\s+([\d,]+)/i) || viewsText.match(/^([\d,]+)/);
      return listingId && viewsMatch ? { listing_id: listingId, views: Number(viewsMatch[1].replace(/,/g, "")) } : null;
    }).filter(Boolean);
  }

  function nextActiveListingsButton() {
    return Array.from(document.querySelectorAll("button,a")).find((element) => {
      const label = clean(element.getAttribute("aria-label") || element.innerText || element.textContent);
      const disabled = element.disabled || element.getAttribute("aria-disabled") === "true";
      return !disabled && /^(next|next page)$/i.test(label) && visible(element);
    }) || null;
  }

  async function captureActiveListingViews() {
    setRunnerStatus("Reading eBay's rolling 30-day listing views...", "working", 10);
    await waitFor(() => activeListingViewRows().length ? true : null, 30000, 500);
    const pageSize = Array.from(document.querySelectorAll("select.listbox__native")).find((select) =>
      Array.from(select.options || []).some((option) => option.value === "200")
    );
    if (pageSize && pageSize.value !== "200") {
      pageSize.value = "200";
      pageSize.dispatchEvent(new Event("change", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    const captured = new Map();
    for (let page = 0; page < 100; page += 1) {
      const rows = activeListingViewRows();
      rows.forEach((row) => captured.set(row.listing_id, row));
      setRunnerStatus(`Captured views for ${captured.size} active listing${captured.size === 1 ? "" : "s"}...`, "working", Math.min(35, 15 + page * 2));
      const next = nextActiveListingsButton();
      if (!next) break;
      const firstListingId = rows[0]?.listing_id || "";
      next.click();
      await waitFor(() => {
        const nextRows = activeListingViewRows();
        return nextRows.length && nextRows[0]?.listing_id !== firstListingId ? true : null;
      }, 30000, 500);
    }
    const rows = Array.from(captured.values());
    const response = await fetch(`${API}/ebay/sync-runs/listing-views`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_key: context.accountKey, run_id: context.runId, rows }),
    });
    if (!response.ok) throw new Error(await response.text());
    const result = await response.json();
    setRunnerStatus(`Saved views for ${result.captured} listing${result.captured === 1 ? "" : "s"}. Opening the full Active Listings report...`, "working", 40);
    location.href = `https://www.ebay.com/sh/reports/downloads#autozs_sync_run=${encodeURIComponent(context.runId)}&autozs_account_key=${encodeURIComponent(context.accountKey)}&autozs_report_type=${encodeURIComponent(context.reportType)}`;
  }

  function exactButton(text, root = document) {
    return Array.from(root.querySelectorAll("button")).find((button) => visible(button) && clean(button.innerText || button.textContent) === text);
  }

  if (onActiveListings) {
    try {
      await captureActiveListingViews();
    } catch (error) {
      const message = error?.message || String(error);
      setRunnerStatus(`AutoZS view capture needs attention: ${message}`, "error", 100);
      patchRun({ status: "needs_review", message: `Automatic Seller Hub view capture failed: ${message}` }).catch(() => {});
    }
    return;
  }

  function selectRadioValue(token) {
    const input = Array.from(document.querySelectorAll('input[type="radio"]')).find((radio) => visible(radio.closest('[role="dialog"]')) && String(radio.value || "").includes(token));
    if (!input) return false;
    const label = Array.from(document.querySelectorAll("label")).find((candidate) => candidate.htmlFor === input.id);
    (label || input).click();
    return true;
  }

  function reportRows() {
    return Array.from(document.querySelectorAll('[role="row"]')).map((row) => {
      const cells = Array.from(row.querySelectorAll('[role="gridcell"]')).map((cell) => clean(cell.innerText || cell.textContent));
      return {
        row,
        cells,
        source: cells[0] || "",
        type: cells[1] || "",
        reference: cells[2] || "",
        requested: cells[3] || "",
        status: cells[4] || "",
      };
    }).filter((item) => item.cells.length >= 5 && /all active listings/i.test(item.type));
  }

  async function requestActiveListingsReport() {
    const existingReferences = new Set(reportRows().map((row) => row.reference).filter(Boolean));
    const openButton = await waitFor(() => exactButton("Download report"));
    openButton.click();
    const sourceButton = await waitFor(() => Array.from(document.querySelectorAll('button[name="name"]')).find((button) => visible(button) && /select report source/i.test(clean(button.innerText))));
    sourceButton.click();
    await waitFor(() => selectRadioValue('"SOURCE":"LISTINGS"'));
    const typeButton = await waitFor(() => Array.from(document.querySelectorAll("button")).find((button) => visible(button) && /select report type/i.test(clean(button.innerText))));
    typeButton.click();
    await waitFor(() => selectRadioValue('"TYPE":"ALL_LISTINGS"'));
    const dialog = await waitFor(() => Array.from(document.querySelectorAll('[role="dialog"]')).find((element) => visible(element) && /^Download report/i.test(clean(element.innerText))));
    const submit = await waitFor(() => {
      const button = exactButton("Download", dialog);
      return button && !button.disabled ? button : null;
    });
    setRunnerStatus("Starting the eBay Active Listings report download...", "working", 45);
    await prepareReportDownloadContext();
    submit.click();
    await patchRun({
      phase: "waiting_for_report",
      message: "eBay is generating and downloading a fresh Active Listings report.",
      increment_attempts: true,
    });
    const createdRow = await waitFor(() => {
      const row = reportRows().find((item) => item.reference && !existingReferences.has(item.reference));
      if (row) return row;
      return readRun().then((latest) => latest.report_filename || latest.status === "completed" ? { downloaded: true } : null);
    }, REPORT_CREATE_TIMEOUT_MS, 2000);
    if (createdRow.downloaded) return null;
    await patchRun({
      phase: "waiting_for_report",
      message: `Waiting for eBay report ${createdRow.reference} to finish.`,
      report_reference: createdRow.reference,
    });
    return createdRow.reference;
  }

  async function downloadCompletedReport(reference) {
    const completed = await waitFor(() => {
      const row = reportRows().find((item) => item.reference === reference);
      if (!row || !/completed/i.test(row.status)) return null;
      return row;
    }, REPORT_COMPLETE_TIMEOUT_MS, 2000);
    const button = exactButton("Download", completed.row);
    if (!button) throw new Error(`eBay report ${reference} completed without a Download button.`);
    setRunnerStatus(`Downloading completed eBay report ${reference}.`, "working", 75);
    await prepareReportDownloadContext();
    await patchRun({
      phase: "downloading_report",
      message: `Downloading completed eBay report ${reference}.`,
      report_reference: reference,
    });
    button.click();
    setRunnerStatus("Report downloaded. AutoZS is importing it now.", "working", 85);
  }

  try {
    setRunnerStatus("AutoZS is preparing the Active Listings report...", "working", 5);
    const account = typeof reportEbayBrowserAccount === "function" ? await reportEbayBrowserAccount(context.accountKey) : null;
    if (account && account.can_list === false) throw new Error(account.message || "The signed-in eBay account does not match this store.");
    let run = await readRun();
    if (["completed", "failed", "needs_review"].includes(run.status)) {
      setRunnerStatus(run.message || `Sync ${run.status}.`, run.status, run.status === "completed" ? 100 : 95);
      if (run.status === "completed") setTimeout(closeReportRunnerTab, 800);
      return;
    }
    setRunnerStatus("Seller Hub Reports opened and the account matched.", "working", 15);
    await patchRun({ phase: "report_page_ready", message: "Seller Hub Reports opened and the account matched." });
    let reference = run.report_reference;
    if (!reference) {
      setRunnerStatus("Requesting a fresh Active Listings report from eBay.", "working", 30);
      await patchRun({ phase: "requesting_report", message: "Requesting a fresh Active Listings report from eBay." });
      reference = await requestActiveListingsReport();
    }
    if (!reference) {
      setRunnerStatus("Report downloaded. AutoZS is importing it now.", "working", 85);
      await waitForImportCompletionAndClose();
      return;
    }
    setRunnerStatus(`Waiting for eBay report ${reference}...`, "working", 60);
    await downloadCompletedReport(reference);
    await waitForImportCompletionAndClose();
  } catch (error) {
    const message = error?.message || String(error);
    setRunnerStatus(`AutoZS report sync needs attention: ${message}`, "error", 100);
    patchRun({ status: "needs_review", message: `Automatic Active Listings report failed: ${message}` }).catch(() => {});
  }
})();
