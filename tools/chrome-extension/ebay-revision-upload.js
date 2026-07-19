(async () => {
  if (window.__autozsEbayRevisionUploadStarted) return;
  const params = new URLSearchParams(location.search || "");
  const batchId = Number(params.get("autozs_revision_batch"));
  const accountKey = params.get("autozs_account_key") || "manual";
  if (!batchId || !/^\/sh\/reports\/uploads/i.test(location.pathname || "")) return;
  if (typeof readAutozsWorkerMode === "function" && await readAutozsWorkerMode() !== "operations") return;
  window.__autozsEbayRevisionUploadStarted = true;

  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (element) => Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));

  const UPLOAD_CONTROL_TIMEOUT_MS = 2 * 60 * 1000;
  const RESULT_TIMEOUT_MS = 5 * 60 * 1000;
  const logoUrl = typeof chrome !== "undefined" && chrome.runtime?.getURL
    ? chrome.runtime.getURL("assets/autozs-logo.png")
    : "";

  function ensureRevisionProgressOverlay() {
    if (!document?.getElementById || !document?.createElement || !document?.documentElement?.appendChild) {
      return null;
    }
    let host = document.getElementById("autozs-revision-progress-host");
    if (host?.shadowRoot) return host;
    host = document.createElement("div");
    host.id = "autozs-revision-progress-host";
    host.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:auto";
    if (!host.attachShadow) return null;
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
          width: min(410px, calc(100vw - 48px));
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
          line-height: 1.35;
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
        .progress-note {
          color: var(--az-muted);
          font-size: 11px;
          text-align: center;
        }
        :host([data-state="error"]) .progress-fill { background: #ff6b6b; }
        :host([data-state="complete"]) .progress-fill { background: #56d88a; }
      </style>
      <div class="progress-overlay" role="status" aria-live="polite">
        <div class="progress-card">
          ${logoUrl ? `<img class="logo" src="${logoUrl}" alt="AutoZS" draggable="false" />` : ""}
          <div class="progress-title">AutoZS is working</div>
          <div id="progress-label" class="progress-label">Preparing eBay price revision...</div>
          <div class="progress-track" aria-hidden="true"><div id="progress-fill" class="progress-fill"></div></div>
          <div id="progress-percent" class="progress-percent">0%</div>
          <div class="progress-note">Keep this tab open until AutoZS finishes.</div>
        </div>
      </div>
    `;
    document.documentElement.appendChild(host);
    return host;
  }

  function setRevisionProgress(text, percent = 0, state = "working") {
    const host = ensureRevisionProgressOverlay();
    if (!host?.shadowRoot) return;
    const shadow = host.shadowRoot;
    const safePercent = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
    host.dataset.state = state;
    const label = shadow.querySelector("#progress-label");
    const fill = shadow.querySelector("#progress-fill");
    const percentLabel = shadow.querySelector("#progress-percent");
    if (label) label.textContent = text;
    if (fill) fill.style.width = `${safePercent}%`;
    if (percentLabel) percentLabel.textContent = `${safePercent}%`;
  }

  async function waitFor(find, timeout = 30000, interval = 300, step = "revision-upload step") {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const value = await find();
      if (value) return value;
      await new Promise((resolve) => setTimeout(resolve, interval));
    }
    throw new Error(`eBay did not finish the expected ${step} in time.`);
  }

  async function readBatch() {
    setRevisionProgress("Reading the AutoZS revision batch...", 8);
    const response = await fetch(`${API}/ebay/revision-batches/${batchId}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }

  async function patchBatch(payload) {
    const response = await fetch(`${API}/ebay/revision-batches/${batchId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }

  async function prepareResultDownload() {
    setRevisionProgress("Preparing the eBay result download watcher...", 70);
    const response = await chrome.runtime.sendMessage({
      type: "autozs-ebay-revision-result-context",
      batchId,
      accountKey,
    });
    if (!response?.ok) throw new Error(response?.error || "AutoZS could not prepare the eBay result download.");
  }

  function exactButton(text, root = document) {
    return Array.from(root.querySelectorAll("button")).find(
      (button) => visible(button) && clean(button.innerText || button.textContent) === text
    );
  }

  function actionControls(root = document) {
    return Array.from(root.querySelectorAll('button, a, [role="button"], label')).filter((element) => visible(element));
  }

  function controlText(element) {
    return clean([
      element.innerText || element.textContent,
      element.getAttribute("aria-label"),
      element.getAttribute("title"),
    ].filter(Boolean).join(" "));
  }

  function buttonDisabled(element) {
    return Boolean(element.disabled || element.getAttribute("aria-disabled") === "true");
  }

  function uploadEntryControl() {
    const exact = exactButton("Upload template");
    if (exact) return exact;
    return actionControls().find((element) => {
      const text = controlText(element).toLowerCase();
      return /upload/.test(text) && !/download|result|history/.test(text) && !buttonDisabled(element);
    });
  }

  function uploadSubmitControl(root = document) {
    return actionControls(root).find((element) => {
      const text = controlText(element).toLowerCase();
      return !buttonDisabled(element)
        && (/^upload$/.test(text) || /upload (file|template|report|csv)/.test(text) || /submit|continue/.test(text));
    });
  }

  function uploadRows() {
    return Array.from(document.querySelectorAll('[role="row"], tr')).map((row) => {
      const cells = Array.from(row.querySelectorAll('[role="gridcell"], td, th')).map((cell) => clean(cell.innerText || cell.textContent));
      return { row, cells, text: clean(row.innerText || row.textContent) };
    }).filter((item) => item.cells.length >= 3);
  }

  function filenameMatchTerms(filename) {
    const normalized = clean(filename).toLowerCase();
    const stem = normalized.replace(/\.(csv|tsv|txt|zip)$/i, "");
    return Array.from(new Set([normalized, stem].filter((term) => term.length >= 12)));
  }

  function rowMatchesUploadFilename(rowText, filename) {
    const text = clean(rowText).toLowerCase();
    return filenameMatchTerms(filename).some((term) => text.includes(term));
  }

  function matchingUploadRow(filename) {
    return uploadRows().find((item) => rowMatchesUploadFilename(item.text, filename));
  }

  function resultDownloadControl(row) {
    const controls = Array.from(row.querySelectorAll("a,button,[role=\"button\"]"));
    const outputLink = controls.find((element) => {
      const href = clean(element.getAttribute("href"));
      return /[?&]filetype=output(?:&|$)/i.test(href);
    });
    if (outputLink) return outputLink;
    return controls.filter(visible).find((element) => {
      const text = clean(element.innerText || element.textContent);
      const label = clean(element.getAttribute("aria-label"));
      return /download.*result|result.*download/i.test(`${text} ${label}`);
    });
  }

  function attachBatchFile(batch) {
    const input = document.querySelector('#file-input[type="file"], input[type="file"][accept*=".csv"], input[type="file"]');
    if (!input) return false;
    if (input.files?.length === 1 && input.files[0]?.name === batch.filename) return true;
    try {
      const file = new File([batch.csv_content], batch.filename, { type: "text/csv;charset=utf-8" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return input.files?.length === 1 && input.files[0]?.name === batch.filename;
    } catch {
      return false;
    }
  }

  async function submitPreparedBatch(batch) {
    setRevisionProgress(`Opening eBay upload controls for ${batch.filename}...`, 18);
    if (!document.querySelector('#file-input[type="file"]')) {
      const open = await waitFor(
        uploadEntryControl,
        UPLOAD_CONTROL_TIMEOUT_MS,
        500,
        "Seller Hub upload-template control"
      );
      await patchBatch({ status: "prepared", message: `Opening eBay upload controls for ${batch.filename}.` });
      open.click();
    }
    setRevisionProgress(`Attaching ${batch.filename} to eBay...`, 34);
    await waitFor(
      () => attachBatchFile(batch),
      UPLOAD_CONTROL_TIMEOUT_MS,
      500,
      "eBay CSV file input"
    );
    setRevisionProgress("Finding eBay's upload button...", 48);
    const dialog = await waitFor(
      () => Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"]')).find(visible) || document,
      UPLOAD_CONTROL_TIMEOUT_MS,
      500,
      "eBay upload dialog"
    );
    const upload = await waitFor(
      () => uploadSubmitControl(dialog),
      UPLOAD_CONTROL_TIMEOUT_MS,
      500,
      "eBay upload submit button"
    );
    await prepareResultDownload();
    setRevisionProgress("Uploading the price revision sheet to eBay...", 62);
    await patchBatch({ status: "uploading", message: `Uploading ${batch.filename} to eBay Seller Hub.` });
    upload.click();
    setRevisionProgress("eBay accepted the sheet. Waiting for the result report...", 78);
    await patchBatch({ status: "waiting_results", message: "eBay accepted the revision sheet; waiting for its result report." });
  }

  async function waitForResult(batch) {
    setRevisionProgress("Waiting for eBay to process the result row...", 82);
    const row = await waitFor(() => {
      const match = matchingUploadRow(batch.filename);
      if (!match) return null;
      if (/failed|error|rejected/i.test(match.text)) throw new Error(match.text);
      return /completed|complete|processed|success/i.test(match.text) ? match : null;
    }, RESULT_TIMEOUT_MS, 2000, "eBay upload result row");
    const download = resultDownloadControl(row.row);
    if (!download) throw new Error("eBay completed the upload without exposing a result download.");
    await prepareResultDownload();
    setRevisionProgress("Downloading the eBay result report back into AutoZS...", 94);
    download.click();
    setRevisionProgress("Result download started. AutoZS will import it next.", 100, "complete");
  }

  try {
    setRevisionProgress("Checking the signed-in eBay account...", 4);
    const account = typeof reportEbayBrowserAccount === "function" ? await reportEbayBrowserAccount(accountKey) : null;
    if (account && account.can_list === false) throw new Error(account.message || "The signed-in eBay account does not match this revision batch.");
    let batch = await readBatch();
    if (batch.status === "completed") return;
    if (batch.status === "prepared") {
      await submitPreparedBatch(batch);
      batch = await readBatch();
    }
    if (["uploading", "waiting_results", "needs_review", "failed"].includes(batch.status)) await waitForResult(batch);
  } catch (error) {
    const message = error?.message || String(error);
    setRevisionProgress(`AutoZS needs attention: ${message}`, 100, "error");
    patchBatch({ status: "needs_review", message: `Automatic eBay revision upload needs attention: ${message}` }).catch(() => {});
  }
})();
