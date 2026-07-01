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
  if (!context || !/^\/sh\/reports\/downloads/i.test(location.pathname || "")) return;
  window.__autozsEbayReportRunnerStarted = true;

  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (element) => Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));

  async function waitFor(find, timeout = 30000, interval = 300) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const value = find();
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

  function setRunnerStatus(text, state = "working") {
    let panel = document.getElementById("autozs-report-runner-status");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "autozs-report-runner-status";
      panel.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:2147483647;max-width:360px;padding:12px 14px;border:1px solid #355047;border-radius:8px;background:#101412;color:#edf4ef;font:600 13px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;box-shadow:0 16px 38px rgba(0,0,0,.38)";
      document.documentElement.appendChild(panel);
    }
    panel.dataset.state = state;
    panel.textContent = text;
  }

  function exactButton(text, root = document) {
    return Array.from(root.querySelectorAll("button")).find((button) => visible(button) && clean(button.innerText || button.textContent) === text);
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
    submit.click();
    await patchRun({
      phase: "waiting_for_report",
      message: "eBay is generating a fresh Active Listings report.",
      increment_attempts: true,
    });
    const createdRow = await waitFor(() => reportRows().find((row) => row.reference && !existingReferences.has(row.reference)), 45000, 500);
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
    }, 180000, 1500);
    const button = exactButton("Download", completed.row);
    if (!button) throw new Error(`eBay report ${reference} completed without a Download button.`);
    const response = await chrome.runtime.sendMessage({ type: "autozs-ebay-report-sync-context", ...context });
    if (!response?.ok) throw new Error(response?.error || "AutoZS could not prepare the report download.");
    await patchRun({
      phase: "downloading_report",
      message: `Downloading completed eBay report ${reference}.`,
      report_reference: reference,
    });
    button.click();
    setRunnerStatus("Report downloaded. AutoZS is importing it now.", "complete");
  }

  try {
    setRunnerStatus("AutoZS is preparing the Active Listings report...");
    const account = typeof reportEbayBrowserAccount === "function" ? await reportEbayBrowserAccount(context.accountKey) : null;
    if (account && account.can_list === false) throw new Error(account.message || "The signed-in eBay account does not match this store.");
    let run = await readRun();
    if (["completed", "failed", "needs_review"].includes(run.status)) {
      setRunnerStatus(run.message || `Sync ${run.status}.`, run.status);
      return;
    }
    await patchRun({ phase: "report_page_ready", message: "Seller Hub Reports opened and the account matched." });
    let reference = run.report_reference;
    if (!reference) {
      await patchRun({ phase: "requesting_report", message: "Requesting a fresh Active Listings report from eBay." });
      reference = await requestActiveListingsReport();
    }
    setRunnerStatus(`Waiting for eBay report ${reference}...`);
    await downloadCompletedReport(reference);
  } catch (error) {
    const message = error?.message || String(error);
    setRunnerStatus(`AutoZS report sync needs attention: ${message}`, "error");
    patchRun({ status: "needs_review", message: `Automatic Active Listings report failed: ${message}` }).catch(() => {});
  }
})();
