(async () => {
  if (window.__autozsEbayRevisionUploadStarted) return;
  const params = new URLSearchParams(location.search || "");
  const batchId = Number(params.get("autozs_revision_batch"));
  const accountKey = params.get("autozs_account_key") || "manual";
  if (!batchId || !/^\/sh\/reports\/uploads/i.test(location.pathname || "")) return;
  window.__autozsEbayRevisionUploadStarted = true;

  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (element) => Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));

  const UPLOAD_CONTROL_TIMEOUT_MS = 2 * 60 * 1000;
  const RESULT_TIMEOUT_MS = 5 * 60 * 1000;

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
    await waitFor(
      () => attachBatchFile(batch),
      UPLOAD_CONTROL_TIMEOUT_MS,
      500,
      "eBay CSV file input"
    );
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
    await patchBatch({ status: "uploading", message: `Uploading ${batch.filename} to eBay Seller Hub.` });
    upload.click();
    await patchBatch({ status: "waiting_results", message: "eBay accepted the revision sheet; waiting for its result report." });
  }

  async function waitForResult(batch) {
    const row = await waitFor(() => {
      const match = matchingUploadRow(batch.filename);
      if (!match) return null;
      if (/failed|error|rejected/i.test(match.text)) throw new Error(match.text);
      return /completed|complete|processed|success/i.test(match.text) ? match : null;
    }, RESULT_TIMEOUT_MS, 2000, "eBay upload result row");
    const download = resultDownloadControl(row.row);
    if (!download) throw new Error("eBay completed the upload without exposing a result download.");
    await prepareResultDownload();
    download.click();
  }

  try {
    const account = typeof reportEbayBrowserAccount === "function" ? await reportEbayBrowserAccount(accountKey) : null;
    if (account && account.can_list === false) throw new Error(account.message || "The signed-in eBay account does not match this revision batch.");
    let batch = await readBatch();
    if (["completed", "needs_review", "failed"].includes(batch.status)) return;
    if (batch.status === "prepared") {
      await submitPreparedBatch(batch);
      batch = await readBatch();
    }
    if (["uploading", "waiting_results"].includes(batch.status)) await waitForResult(batch);
  } catch (error) {
    const message = error?.message || String(error);
    patchBatch({ status: "needs_review", message: `Automatic eBay revision upload needs attention: ${message}` }).catch(() => {});
  }
})();
