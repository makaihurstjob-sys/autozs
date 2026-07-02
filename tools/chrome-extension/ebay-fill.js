(async () => {
  const ASSISTANT_BUILD = "2026-07-02-guarded-revision-runner";
  const existingAssistant = document.getElementById("autozs-ebay-fill-assistant");
  const existingBuild = existingAssistant?.getAttribute?.("data-autozs-build") || "";
  if (window.__autozsEbayFillAssistant && existingBuild === ASSISTANT_BUILD) return;
  if (existingAssistant) existingAssistant.remove();
  window.__autozsEbayFillAssistant = false;

  const params = readAutozsParams();
  const requestedProductId = params.get("autozs_product_id");
  const requestedJobId = params.get("autozs_job_id");
  const requestedRevisionJobId = params.get("autozs_revision_job_id");
  const requestedAccountKey = params.get("autozs_account_key") || "manual";
  const requestedWorkflow = params.get("autozs_workflow") || "";
  const requestedTargetPrice = params.get("autozs_target_price") || "";
  const requestedAutosave = params.get("autozs_autosave") === "1";
  const requestedAutoSubmit = params.get("autozs_autosubmit") === "1";
  const requestedListingScheduleAt = params.get("autozs_listing_schedule_at") || "";
  const requestedFill = params.get("autozs_fill") === "1" || Boolean(requestedProductId);
  if (requestedProductId && !requestedWorkflow) clearAutoWorkflowState();
  if (requestedWorkflow) {
    const existingWorkflow = readAutoWorkflowState();
    const sameRevisionAttempt =
      requestedWorkflow === "revise_price" &&
      existingWorkflow?.mode === "revise_price" &&
      String(existingWorkflow?.revisionJobId || "") === String(requestedRevisionJobId || "");
    const preservedRevisionPhase =
      sameRevisionAttempt && ["submitting", "confirmation_pending", "completed"].includes(existingWorkflow?.phase)
        ? existingWorkflow.phase
        : "opened";
    writeAutoWorkflowState({
      productId: requestedProductId || readSavedProductId(),
      jobId: requestedJobId || "",
      revisionJobId: requestedRevisionJobId || "",
      accountKey: requestedAccountKey,
      mode: requestedWorkflow,
      targetPrice: requestedTargetPrice,
      autosave: requestedAutosave,
      autoSubmit: requestedAutoSubmit,
      listingScheduleAt: requestedListingScheduleAt,
      status: preservedRevisionPhase === "completed" ? "completed" : "running",
      phase: preservedRevisionPhase,
    });
  }
  const activeWorkflow = readAutoWorkflowState();
  const workflowRunning = activeWorkflow && !["completed", "failed"].includes(activeWorkflow.status);
  const savedProductId = readSavedProductId();
  const savedJobId = readSavedJobId();
  const listingEditor = isEbayListingEditorPage();
  const prelistPage = isEbayPrelistPage();
  const assistantPage = listingEditor || prelistPage;
  const waitForBody = () =>
    new Promise((resolve) => {
      if (document.body) return resolve();
      const timer = setInterval(() => {
        if (document.body) {
          clearInterval(timer);
          resolve();
        }
      }, 100);
    });
  if (requestedProductId) writeSavedProductId(requestedProductId);
  if (requestedJobId) writeSavedJobId(requestedJobId);
  else if (requestedProductId) clearSavedJobId();
  if (!assistantPage) {
    await waitForBody();
    if (typeof reportEbayBrowserAccount === "function") reportEbayBrowserAccount("manual").catch(() => {});
    if (activeWorkflow?.mode === "create_draft" && activeWorkflow?.phase === "submitting") {
      startEbayPublishSuccessReporter();
      reportEbayPublishConfirmation().catch(() => {});
    }
    return;
  }
  window.__autozsEbayFillAssistant = true;
  const initialProductId = escapeHtmlAttribute(requestedProductId || activeWorkflow?.productId || savedProductId || "");

  await waitForBody();
  if (requestedWorkflow === "revise_price" || activeWorkflow?.mode === "revise_price") {
    startEbayRevisionSuccessReporter();
  } else {
    startEbayPublishSuccessReporter();
  }

  const logoUrl = (() => {
    try {
      return typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.getURL
        ? chrome.runtime.getURL("assets/autozs-logo.png")
        : "";
    } catch {
      return "";
    }
  })();
  const host = document.createElement("div");
  host.id = "autozs-ebay-fill-assistant";
  host.setAttribute("data-autozs-build", ASSISTANT_BUILD);
  host.style.cssText = "position:fixed;inset:0;z-index:2147483000;pointer-events:none;";
  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      .panel {
        background: var(--az-bg, #111a15);
        border: 1px solid var(--az-line, #2b352f);
        border-radius: 8px;
        box-shadow: 0 12px 34px rgba(0,0,0,.24);
        color: var(--az-ink, #edf4ef);
        font: 10px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        overflow: hidden;
        pointer-events: auto;
        position: absolute;
        right: 18px;
        bottom: 18px;
        width: min(300px, calc(100vw - 36px));
      }
      .head {
        align-items: center;
        border-bottom: 1px solid var(--az-line, #2b352f);
        cursor: pointer;
        display: flex;
        gap: 10px;
        padding: 10px 13px;
      }
      .logo {
        background: #000;
        border-radius: 6px;
        height: 42px;
        object-fit: contain;
        padding: 0;
        pointer-events: none;
        user-select: none;
        -webkit-user-drag: none;
        width: 42px;
      }
      .title {
        display: block;
        flex: 1;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        font-size: 22px;
        font-weight: 800;
        letter-spacing: 0;
        line-height: 1;
      }
      .window-actions {
        align-items: center;
        display: flex;
        gap: 7px;
        margin-left: auto;
      }
      .window-action {
        border: 0;
        border-radius: 50%;
        box-shadow: none;
        cursor: pointer;
        height: 13px;
        padding: 0;
        width: 13px;
      }
      .window-action.minimize { background: #ffc018; }
      .window-action.restore { background: #33c767; }
      .window-action.close { background: #ec4b53; }
      .window-action:focus-visible,
      .assistant-widget:focus-visible,
      button:focus-visible,
      input:focus-visible {
        outline: 2px solid rgba(75, 183, 166, .55);
        outline-offset: 2px;
      }
      .muted, .status {
        color: var(--az-muted, #56625a);
        font-size: 12px;
      }
      .body {
        display: grid;
        gap: 10px;
        padding: 13px;
      }
      .product-row {
        align-items: center;
        display: grid;
        gap: 8px;
        grid-template-columns: max-content 1fr;
      }
      .product-label {
        color: var(--az-ink, #edf4ef);
        font-size: 16px;
        font-weight: 800;
        line-height: 1;
      }
      input, button, textarea {
        border-radius: 6px;
        box-sizing: border-box;
        font: inherit;
        padding: 7px 9px;
        width: 100%;
      }
      input, textarea {
        background: var(--az-field, #101412);
        border: 1px solid var(--az-line, #dfe5dc);
        color: var(--az-ink, #17201b);
      }
      input {
        font-size: 14px;
        height: 37px;
      }
      button {
        background: var(--az-accent, #166b5f);
        border: 0;
        color: #fff;
        cursor: pointer;
        font-weight: 800;
      }
      .primary-action {
        background: var(--az-accent, #4bb7a6);
        border-radius: 7px;
        font-size: 20px;
        line-height: 1;
        padding: 14px 10px;
      }
      button.secondary { background: var(--az-secondary, #263631); }
      button.danger { background: #8f3d2e; }
      .actions { display: grid; gap: 8px; grid-template-columns: 1fr 1fr; }
      .actions .wide { grid-column: 1 / -1; }
      .checklist {
        background: var(--az-soft, #101412);
        border: 1px solid var(--az-line, #dfe5dc);
        border-radius: 6px;
        color: var(--az-ink, #edf4ef);
        font-size: 14px;
        max-height: 130px;
        overflow: auto;
        padding: 8px 10px;
        white-space: pre-wrap;
      }
      .assistant-widget {
        align-items: center;
        background: var(--az-bg, #111a15);
        border: 1px solid var(--az-line, #2b352f);
        border-radius: 8px;
        box-shadow: 0 12px 34px rgba(0,0,0,.28);
        color: var(--az-ink, #edf4ef);
        cursor: pointer;
        display: none;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        gap: 10px;
        padding: 10px 13px;
        pointer-events: auto;
        position: absolute;
        right: 18px;
        bottom: 18px;
        width: min(300px, calc(100vw - 36px));
      }
      .progress-overlay {
        align-items: center;
        background: rgba(10, 14, 12, .74);
        backdrop-filter: blur(3px);
        color: #edf4ef;
        display: none;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        inset: 0;
        justify-content: center;
        pointer-events: auto;
        position: absolute;
      }
      .progress-card {
        align-items: center;
        background: #111a15;
        border: 1px solid #2b352f;
        border-radius: 8px;
        box-shadow: 0 24px 70px rgba(0,0,0,.38);
        display: grid;
        gap: 14px;
        justify-items: center;
        padding: 28px;
        width: min(390px, calc(100vw - 48px));
      }
      .progress-title {
        font-size: 28px;
        font-weight: 850;
        letter-spacing: 0;
        line-height: 1.1;
      }
      .progress-label {
        color: #9aa89f;
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
        background: #4bb7a6;
        height: 100%;
        transition: width .22s ease;
        width: 0%;
      }
      .progress-percent {
        color: #edf4ef;
        font-size: 13px;
        font-weight: 800;
      }
      :host([data-minimized="1"]) .panel { display: none; }
      :host([data-minimized="1"]) .assistant-widget { display: flex; }
      :host([data-progress-active="1"]) .progress-overlay { display: flex; }
    </style>
    <div id="progress-overlay" class="progress-overlay" role="status" aria-live="polite">
      <div class="progress-card">
        ${logoUrl ? `<img class="logo" src="${logoUrl}" alt="AutoZS" draggable="false" />` : ""}
        <div class="progress-title">Auto-ZS in progress</div>
        <div id="progress-label" class="progress-label">Preparing listing...</div>
        <div class="progress-track" aria-hidden="true"><div id="progress-fill" class="progress-fill"></div></div>
        <div id="progress-percent" class="progress-percent">0%</div>
      </div>
    </div>
    <div class="panel">
      <div class="head" tabindex="0" aria-label="Minimize Listing Assistant">
        ${logoUrl ? `<img class="logo" src="${logoUrl}" alt="AutoZS" draggable="false" />` : ""}
        <div class="title">Listing Assistant</div>
        <div class="window-actions" aria-label="Window controls">
          <button id="minimize" class="window-action minimize" type="button" title="Minimize Listing Assistant" aria-label="Minimize Listing Assistant"></button>
          <button id="close" class="window-action close" type="button" title="Close Listing Assistant" aria-label="Close Listing Assistant"></button>
        </div>
      </div>
      <div class="body">
        <div class="product-row">
          <label class="product-label" for="product-id">Product #:</label>
          <input id="product-id" placeholder="AutoZS product id" value="${initialProductId}" />
        </div>
        <button id="fill" class="primary-action">Fill Listing</button>
        <div class="status" id="status">Listing Assistant ready.</div>
        <div class="checklist" id="checklist">Images upload through AutoZS. Final publish stays manual.</div>
      </div>
    </div>
    <div id="restore-widget" class="assistant-widget" role="button" tabindex="0" aria-label="Restore Listing Assistant">
      ${logoUrl ? `<img class="logo" src="${logoUrl}" alt="" draggable="false" />` : ""}
      <div class="title">Listing Assistant</div>
      <div class="window-actions" aria-label="Window controls">
        <span class="window-action restore" aria-hidden="true"></span>
        <button id="close-widget" class="window-action close" type="button" title="Close Listing Assistant" aria-label="Close Listing Assistant"></button>
      </div>
    </div>
  `;
  document.body.appendChild(host);

  const setTheme = (theme) => {
    const dark = theme === "dark";
    host.style.setProperty("--az-bg", dark ? "#171d1a" : "#ffffff");
    host.style.setProperty("--az-field", dark ? "#101412" : "#ffffff");
    host.style.setProperty("--az-soft", dark ? "#101412" : "#f5f7f4");
    host.style.setProperty("--az-ink", dark ? "#edf4ef" : "#17201b");
    host.style.setProperty("--az-muted", dark ? "#9aa89f" : "#56625a");
    host.style.setProperty("--az-line", dark ? "#2b352f" : "#dfe5dc");
    host.style.setProperty("--az-accent", dark ? "#4bb7a6" : "#166b5f");
    host.style.setProperty("--az-secondary", dark ? "#2b3732" : "#263631");
  };
  setTheme(fallbackTheme());
  readAppTheme().then(setTheme).catch(() => {});

  let currentPackage = null;
  let currentJobId = requestedJobId || activeWorkflow?.jobId || (requestedProductId ? "" : savedJobId) || "";
  const status = shadow.querySelector("#status");
  const checklist = shadow.querySelector("#checklist");
  const productIdInput = shadow.querySelector("#product-id");
  const progressLabel = shadow.querySelector("#progress-label");
  const progressFill = shadow.querySelector("#progress-fill");
  const progressPercent = shadow.querySelector("#progress-percent");
  const setStatus = (text) => {
    status.textContent = text;
    status.title = text;
  };
  const setFillProgress = (active, percent = 0, label = "") => {
    if (!active) {
      host.removeAttribute("data-progress-active");
      progressFill.style.width = "0%";
      progressPercent.textContent = "0%";
      progressLabel.textContent = "";
      return;
    }
    const safePercent = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
    host.setAttribute("data-progress-active", "1");
    progressFill.style.width = `${safePercent}%`;
    progressPercent.textContent = `${safePercent}%`;
    progressLabel.textContent = label || "Working on eBay listing...";
  };
  const setAssistantMinimized = (minimized) => {
    if (minimized) host.setAttribute("data-minimized", "1");
    else host.removeAttribute("data-minimized");
  };
  const closeAssistant = () => {
    window.__autozsEbayFillAssistant = false;
    host.remove();
  };

  const loadPackage = async () => {
    const productId = Number(productIdInput.value);
    if (!productId) throw new Error("Enter an AutoZS product id.");
    writeSavedProductId(productId);
    await checkLocalApi();
    const accountStatus = await reportEbayBrowserAccount(currentWorkflowAccountKey());
    if (!accountStatus.can_list) throw new Error(accountStatus.message);
    currentPackage = await fetchEbayListingPackage(productId);
    const workflow = readAutoWorkflowState();
    if (workflow?.mode === "revise_price" && workflow.targetPrice) {
      currentPackage = { ...currentPackage, price: Number(workflow.targetPrice) };
    }
    if (workflow?.listingScheduleAt) {
      currentPackage = {
        ...currentPackage,
        listing_schedule_mode: "scheduled",
        listing_schedule_at: workflow.listingScheduleAt,
      };
    }
    checklist.textContent = listingChecklist(currentPackage);
    setStatus(`Loaded ${currentPackage.sku}: ${currentPackage.title}`);
    return currentPackage;
  };

  const withStatus = async (action, label) => {
    try {
      setStatus(label);
      await action();
    } catch (error) {
      setFillProgress(false);
      setStatus(`Error: ${error.message}`);
      const workflow = readAutoWorkflowState() || {};
      if (workflow.mode === "revise_price" && workflow.revisionJobId) {
        await updateEbayRevisionJob(workflow.revisionJobId, {
          status: "failed",
          message: `Revision automation failed: ${error.message || String(error)}`,
        }).catch(() => {});
        writeAutoWorkflowState({ phase: "failed", status: "failed" });
      }
    }
  };

  const assistantHeader = shadow.querySelector(".head");
  assistantHeader.addEventListener("click", (event) => {
    if (event.target.closest(".close")) return;
    setAssistantMinimized(true);
  });
  assistantHeader.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    setAssistantMinimized(true);
  });
  assistantHeader.addEventListener("contextmenu", (event) => event.preventDefault());
  shadow.querySelector("#close").addEventListener("click", (event) => {
    event.stopPropagation();
    closeAssistant();
  });
  shadow.querySelector("#restore-widget").addEventListener("click", (event) => {
    if (event.target.closest("#close-widget")) return;
    setAssistantMinimized(false);
  });
  shadow.querySelector("#restore-widget").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    setAssistantMinimized(false);
  });
  shadow.querySelector("#restore-widget").addEventListener("contextmenu", (event) => event.preventDefault());
  shadow.querySelector("#close-widget").addEventListener("click", (event) => {
    event.stopPropagation();
    closeAssistant();
  });
  shadow.querySelector("#fill").addEventListener("click", () =>
    withStatus(async () => {
      const pkg = currentPackage || (await loadPackage());
      if (isEbayPrelistPage()) {
        const prelistResult = await prepareEbayPrelist(pkg);
        checklist.textContent = `${prelistResult.lines.join("\n")}\n\nImages upload through AutoZS. Final publish stays manual.`;
        if (currentJobId) {
          await updateListingJob(currentJobId, {
            status: "needs_review",
            message: `${prelistResult.message} Choose a catalog match/category, then run Fill Listing on the listing editor.`,
          });
        }
        setStatus(`${prelistResult.message} Choose a match/category, then run Fill Listing on the editor.`);
        return;
      }
      if (!isEbayListingEditorPage()) {
        const message = "This page is not the eBay listing editor. Open Create listing or an eBay draft before filling fields.";
        if (currentJobId) await updateListingJob(currentJobId, { status: "needs_review", message });
        setStatus(message);
        return;
      }
      setAssistantMinimized(true);
      setFillProgress(true, 5, "Preparing eBay listing...");
      const fillResult = await fillEbayListingDraft(pkg, (percent, label) => setFillProgress(true, percent, label));
      setFillProgress(true, 82, "Uploading listing images...");
      const uploadResult = await uploadListingImages(pkg);
      setFillProgress(true, 94, "Running final listing checks...");
      await finishListingEditorView();
      const resultLines = [
        ...fillResult.lines,
        `Images: ${uploadResult.message}`,
        currentJobId ? `Listing job: ${currentJobId}` : "Listing job: none",
      ];
      checklist.textContent = `${resultLines.join("\n")}\n\nFinal publish stays manual.`;
      if (currentJobId) {
        const filledEnough = fillResult.filled >= Math.min(4, fillResult.total);
        if (filledEnough && uploadResult.ok) {
          await updateListingJob(currentJobId, {
            status: "ready_to_save",
            message: `Filled ${fillResult.filled}/${fillResult.total} field group(s); ${uploadResult.message}. Review eBay manually before publishing.`,
          });
          setStatus(`Ready for review. Filled ${fillResult.filled}/${fillResult.total}; ${uploadResult.message}.`);
          setFillProgress(true, 100, "Listing fill complete.");
          await delay(500);
          setFillProgress(false);
          return;
        }
        await updateListingJob(currentJobId, {
          status: "needs_review",
          message: `Manual review needed. Filled ${fillResult.filled}/${fillResult.total}; ${uploadResult.message}.`,
        });
      }
      setStatus(`Manual review needed. Filled ${fillResult.filled}/${fillResult.total}; ${uploadResult.message}.`);
      setFillProgress(true, 100, "Listing fill complete.");
      await delay(500);
      setFillProgress(false);
    }, "Filling listing and uploading images...")
  );

  if (requestedProductId || workflowRunning) {
    withStatus(async () => {
      const pkg = await loadPackage();
      if (readAutoWorkflowState() && requestedWorkflow) {
        await delay(700);
        if (requestedWorkflow !== "revise_price") setAssistantMinimized(true);
        if (requestedWorkflow !== "revise_price") setFillProgress(true, 5, "Preparing eBay listing...");
        const result = requestedWorkflow === "revise_price"
          ? await runPriceRevisionWorkflow(pkg)
          : await runAutoDraftWorkflow(pkg, (percent, label) => setFillProgress(true, percent, label));
        checklist.textContent = `${listingChecklist(pkg)}\n\nWorkflow results:\n${result.lines.join("\n")}`;
        setStatus(result.message);
        setFillProgress(false);
      } else if (workflowRunning) {
        await delay(700);
        if (activeWorkflow?.mode !== "revise_price") setAssistantMinimized(true);
        if (activeWorkflow?.mode !== "revise_price") setFillProgress(true, 5, "Preparing eBay listing...");
        const result = activeWorkflow?.mode === "revise_price"
          ? await runPriceRevisionWorkflow(pkg)
          : await runAutoDraftWorkflow(pkg, (percent, label) => setFillProgress(true, percent, label));
        checklist.textContent = `${listingChecklist(pkg)}\n\nWorkflow results:\n${result.lines.join("\n")}`;
        setStatus(result.message);
        setFillProgress(false);
      }
    }, workflowRunning ? "Resuming eBay draft workflow..." : "Loading package from AutoZS...");
  }
})();

function readAutozsParams() {
  const params = new URLSearchParams(location.search);
  const hash = String(location.hash || "").replace(/^#/, "");
  const hashParams = new URLSearchParams(hash);
  hashParams.forEach((value, key) => {
    if (!params.has(key)) params.set(key, value);
  });
  return params;
}

function isEbayListingEditorPage() {
  return /(^|\.)ebay\.com$/i.test(location.hostname) && /^\/(?:lstng|sl\/list)\b/i.test(location.pathname);
}

function isEbayPrelistPage() {
  return /(^|\.)ebay\.com$/i.test(location.hostname) && /^\/sl\/prelist\b/i.test(location.pathname);
}

function readSavedProductId() {
  try {
    return localStorage.getItem("autozs_last_product_id") || "";
  } catch {
    return "";
  }
}

function readSavedJobId() {
  try {
    return localStorage.getItem("autozs_last_job_id") || "";
  } catch {
    return "";
  }
}

function readAutoWorkflowState() {
  try {
    const raw = localStorage.getItem("autozs_ebay_workflow");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeAutoWorkflowState(update) {
  try {
    const existing = readAutoWorkflowState() || {};
    const next = {
      ...existing,
      ...update,
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem("autozs_ebay_workflow", JSON.stringify(next));
    return next;
  } catch {
    return null;
  }
}

function clearAutoWorkflowState() {
  try {
    localStorage.removeItem("autozs_ebay_workflow");
  } catch {}
}

function detectEbayPublishConfirmation() {
  const text = String(document.body?.innerText || "").replace(/\s+/g, " ").trim();
  const scheduled = /your listing has been scheduled|listing has been scheduled/i.test(text);
  const listed = scheduled || /your listing is (?:live|active)|listing (?:is live|was listed|has been listed)|listed successfully/i.test(text);
  if (!listed) return null;
  const itemLink = [...document.querySelectorAll('a[href*="/itm/"]')].find((link) => /\/itm\/\d+/i.test(link.href || ""));
  const itemId =
    (itemLink?.href || "").match(/\/itm\/(\d+)/i)?.[1] ||
    String(location.href || "").match(/(?:\/itm\/|[?&](?:itemId|itemid)=)(\d{9,15})/i)?.[1] ||
    text.match(/\bID[-:\s]*(\d{9,15})\b/i)?.[1] ||
    "";
  if (!itemId) return null;
  return {
    listingId: itemId,
    status: scheduled ? "scheduled" : "listed",
    message: scheduled ? `Scheduled on eBay as item ${itemId}.` : `Listed on eBay as item ${itemId}.`,
  };
}

async function reportEbayPublishConfirmation() {
  const confirmation = detectEbayPublishConfirmation();
  if (!confirmation) return null;
  const workflow = readAutoWorkflowState() || {};
  const productId = workflow.productId || readSavedProductId();
  if (!productId) return confirmation;
  if (workflow.listingId === confirmation.listingId && workflow.phase === "completed") return confirmation;
  const accountKey = workflow.accountKey || currentWorkflowAccountKey();
  const response = await fetch(`${API}/products/${encodeURIComponent(productId)}/mark-listed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      listing_id: confirmation.listingId,
      account_id: accountKey || "manual",
      environment: "production",
      quantity: 1,
      status: confirmation.status,
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  const jobId = workflow.jobId || readSavedJobId();
  if (jobId) {
    await updateListingJob(jobId, {
      status: "completed",
      message: confirmation.message,
      ebay_draft_id: workflow.draftId || readDraftIdFromUrl() || null,
    });
  }
  writeAutoWorkflowState({
    phase: "completed",
    status: "completed",
    listingId: confirmation.listingId,
  });
  return confirmation;
}

function startEbayPublishSuccessReporter() {
  if (window.__autozsEbayPublishSuccessReporterStarted) return;
  window.__autozsEbayPublishSuccessReporterStarted = true;
  let reporting = false;
  let observer = null;
  const report = async () => {
    if (reporting) return;
    reporting = true;
    try {
      const confirmation = await reportEbayPublishConfirmation();
      if (confirmation && observer) observer.disconnect();
    } catch {
    } finally {
      reporting = false;
    }
  };
  [1000, 4000, 10000].forEach((delay) => setTimeout(report, delay));
  if (typeof MutationObserver !== "undefined" && document.body) {
    observer = new MutationObserver(() => {
      if (detectEbayPublishConfirmation()) report();
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }
}

function detectEbayRevisionConfirmation() {
  const text = String(document.body?.innerText || "").replace(/\s+/g, " ").trim();
  if (!/listing (?:was |has been )?(?:updated|revised)|revision (?:was )?(?:submitted|successful)|changes (?:are|were) live/i.test(text)) {
    return null;
  }
  return { message: "eBay confirmed the listing price revision." };
}

async function reportEbayRevisionConfirmation() {
  const confirmation = detectEbayRevisionConfirmation();
  if (!confirmation) return null;
  const workflow = readAutoWorkflowState() || {};
  if (!workflow.revisionJobId || workflow.phase === "completed") return confirmation;
  await updateEbayRevisionJob(workflow.revisionJobId, {
    status: "completed",
    message: confirmation.message,
  });
  writeAutoWorkflowState({ phase: "completed", status: "completed" });
  return confirmation;
}

function startEbayRevisionSuccessReporter() {
  if (window.__autozsEbayRevisionSuccessReporterStarted) return;
  window.__autozsEbayRevisionSuccessReporterStarted = true;
  let reporting = false;
  const report = async () => {
    if (reporting) return;
    reporting = true;
    try {
      await reportEbayRevisionConfirmation();
    } catch {
    } finally {
      reporting = false;
    }
  };
  [1000, 4000, 10000].forEach((delay) => setTimeout(report, delay));
  const observer = new MutationObserver(report);
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
}

function startAutoWorkflow(pkg, options = {}) {
  return writeAutoWorkflowState({
    productId: String(pkg.product_id || readSavedProductId() || ""),
    jobId: readSavedJobId(),
    accountKey: currentWorkflowAccountKey(),
    mode: "create_draft",
    autosave: options.autosave !== false,
    autoSubmit: options.autoSubmit === true,
    status: "running",
    phase: isEbayListingEditorPage() ? "editor" : isEbayPrelistPage() ? "prelist" : "started",
  });
}

function writeSavedProductId(productId) {
  try {
    if (productId) localStorage.setItem("autozs_last_product_id", String(productId));
  } catch {}
}

function writeSavedJobId(jobId) {
  try {
    if (jobId) localStorage.setItem("autozs_last_job_id", String(jobId));
  } catch {}
}

function clearSavedJobId() {
  try {
    localStorage.removeItem("autozs_last_job_id");
  } catch {}
}

function escapeHtmlAttribute(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function fillEbayListingDraft(pkg, onProgress = () => {}) {
  const results = [];
  const tryFill = async (label, value, filler) => {
    const ok = value !== null && value !== undefined && String(value).trim() && (await filler(value));
    results.push(`${ok ? "OK" : "Review"} ${label}`);
    return Boolean(ok);
  };
  const tryApply = async (label, action) => {
    const ok = await action();
    results.push(`${ok ? "OK" : "Review"} ${label}`);
    return Boolean(ok);
  };
  const fills = [];
  onProgress(12, "Filling title...");
  fills.push(await tryFill("title", pkg.title, (value) => fillEbayFieldByHints(["title", "listing title"], value)));
  onProgress(22, "Filling price...");
  fills.push(await tryFill("price", pkg.price, (value) => fillEbayFieldByHints(["price", "buy it now", "fixed price"], Number(value).toFixed(2))));
  onProgress(32, "Filling SKU...");
  fills.push(await tryFill("sku", pkg.sku, (value) => fillEbayFieldByHints(["sku", "custom label", "custom sku"], value)));
  onProgress(42, "Filling quantity...");
  fills.push(await tryFill("quantity", pkg.quantity || 1, (value) => fillEbayFieldByHints(["quantity", "available quantity"], String(value))));
  onProgress(52, "Filling HTML description...");
  fills.push(await tryFill("description", pkg.description, (value) => fillDescription(value)));
  onProgress(62, "Applying item specifics...");
  const appliedSuggestedSpecifics = await applySuggestedItemSpecifics();
  if (appliedSuggestedSpecifics) results.push("OK suggested item specifics");
  const itemSpecifics = inferredItemSpecifics(pkg);
  if (!itemSpecifics.Brand) itemSpecifics.Brand = "Unbranded";
  const specificsEntries = Object.entries(itemSpecifics);
  let specificsIndex = 0;
  for (const [key, value] of Object.entries(itemSpecifics)) {
    specificsIndex += 1;
    onProgress(62 + Math.round((specificsIndex / Math.max(1, specificsEntries.length)) * 10), `Applying ${key}...`);
    fills.push(await tryFill(`item specific ${key}`, value, async (specificValue) => fillEbayItemSpecific(key, specificValue)));
  }
  if (pkg.offers_enabled === false) {
    onProgress(74, "Disabling offers...");
    fills.push(await tryApply("offers disabled", () => setCheckboxByHints(["best offer", "allow offers"], false)));
  }
  if (pkg.listing_schedule_at) {
    onProgress(76, "Applying schedule...");
    fills.push(await tryApply("schedule listing", () => applyListingSchedule(pkg)));
  }
  onProgress(78, "Applying shipping defaults...");
  fills.push(await tryApply("shipping defaults", () => applyShippingDefaults(pkg)));
  return { filled: fills.filter(Boolean).length, total: fills.length, lines: results };
}

async function runPriceRevisionWorkflow(pkg) {
  const existingWorkflow = readAutoWorkflowState() || {};
  if (["submitting", "confirmation_pending", "completed"].includes(existingWorkflow.phase)) {
    const confirmation = await reportEbayRevisionConfirmation();
    return {
      lines: [confirmation ? "OK eBay confirmed revision" : "Waiting for authoritative eBay confirmation"],
      message: confirmation
        ? confirmation.message
        : "AutoZS already submitted this revision and will not submit it again without a new attempt.",
      terminal: Boolean(confirmation) || existingWorkflow.phase === "completed",
    };
  }
  if (!isEbayListingEditorPage()) {
    return {
      lines: ["Review eBay page"],
      message: "Waiting for eBay to open the listing revision editor.",
      terminal: false,
    };
  }
  await waitForEditorReady();
  const targetPrice = Number(readAutoWorkflowState()?.targetPrice || pkg.price);
  const filled = Number.isFinite(targetPrice)
    && await fillEbayFieldByHints(["price", "buy it now", "fixed price"], targetPrice.toFixed(2));
  await finishListingEditorView();
  const revisionJobId = readAutoWorkflowState()?.revisionJobId;
  const workflow = readAutoWorkflowState() || {};
  if (!filled) {
    if (revisionJobId) {
      await updateEbayRevisionJob(revisionJobId, {
        status: "failed",
        message: `Could not find the eBay price field for $${targetPrice.toFixed(2)}.`,
      });
    }
    writeAutoWorkflowState({ phase: "failed", status: "failed" });
    return {
      lines: [`Review price $${targetPrice.toFixed(2)}`],
      message: "Could not update the eBay price field.",
      terminal: true,
    };
  }
  if (revisionJobId) {
    await updateEbayRevisionJob(revisionJobId, {
      status: "running",
      message: `Filled the eBay price field with $${targetPrice.toFixed(2)}.`,
    });
  }
  if (workflow.autoSubmit === true) {
    const submitResult = await submitPriceRevision(targetPrice);
    if (!submitResult.ok) {
      if (revisionJobId) {
        await updateEbayRevisionJob(revisionJobId, { status: "failed", message: submitResult.message });
      }
      writeAutoWorkflowState({ phase: "failed", status: "failed" });
      return { lines: [`OK price $${targetPrice.toFixed(2)}`, "Review revision submission"], message: submitResult.message, terminal: true };
    }
    if (revisionJobId) {
      await updateEbayRevisionJob(revisionJobId, {
        status: "running",
        message: `Submitted eBay price revision to $${targetPrice.toFixed(2)}; waiting for confirmation.`,
      });
    }
    writeAutoWorkflowState({ phase: "submitting", status: "running" });
    const confirmed = await waitForCondition(() => Boolean(detectEbayRevisionConfirmation()), 20000, 500);
    if (confirmed) {
      await reportEbayRevisionConfirmation();
    } else {
      const diagnostic = ebayRevisionConfirmationDiagnostic();
      if (revisionJobId) {
        await updateEbayRevisionJob(revisionJobId, {
          status: "paused",
          message: `Submission clicked, but eBay confirmation was not recognized. ${diagnostic}`,
        });
      }
      writeAutoWorkflowState({ phase: "confirmation_pending", status: "running" });
    }
    return {
      lines: [`OK price $${targetPrice.toFixed(2)}`, "OK submitted revision"],
      message: confirmed
        ? "eBay confirmed the price revision."
        : "Submission clicked once; paused until AutoZS can prove the eBay result.",
      terminal: confirmed,
    };
  }
  writeAutoWorkflowState({
    phase: "ready_to_submit",
    status: "running",
  });
  return {
    lines: [`OK price $${targetPrice.toFixed(2)}`],
    message: `Price updated to $${targetPrice.toFixed(2)} in the editor. Review, then submit the revision on eBay.`,
    terminal: true,
  };
}

function findPriceRevisionSubmitButton() {
  const candidates = [...document.querySelectorAll("button, [role='button'], input[type='submit']")]
    .filter(isVisible)
    .filter((element) => !element.disabled && element.getAttribute("aria-disabled") !== "true")
    .map((element) => ({
      element,
      label: String(element.value || element.innerText || element.textContent || element.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim(),
    }));
  const patterns = [
    /^submit revisions?$/i,
    /^revise (?:it|listing)$/i,
    /^update listing$/i,
    /^save changes$/i,
  ];
  for (const pattern of patterns) {
    const match = candidates.find((candidate) => pattern.test(candidate.label));
    if (match) return match.element;
  }
  return null;
}

function ebayRevisionConfirmationDiagnostic() {
  const lines = String(document.body?.innerText || "")
    .split("\n")
    .map((value) => value.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .filter((value) => /listing|revision|revis|updated?|changes?|saved?|success|error|problem/i.test(value))
    .slice(0, 3)
    .join(" | ")
    .slice(0, 360);
  const pageTitle = String(document.title || "").replace(/\s+/g, " ").trim().slice(0, 120);
  const path = String(location.pathname || "").slice(0, 160);
  return `Page ${path || "/"}; title ${pageTitle || "unknown"}; status ${lines || "no matching status text"}.`;
}

async function submitPriceRevision(targetPrice) {
  const issue = detectEbaySubmissionIssue();
  if (issue) return { ok: false, message: issue };
  const button = findPriceRevisionSubmitButton();
  if (!button) return { ok: false, message: "Could not find eBay's final revision button. AutoZS did not submit." };
  const clicked = await clickEbayElement(button);
  return clicked
    ? { ok: true, message: `Submitted eBay price revision to $${Number(targetPrice).toFixed(2)}.` }
    : { ok: false, message: "Could not click eBay's final revision button." };
}

async function runAutoDraftWorkflow(pkg, onProgress = () => {}) {
  const workflow = readAutoWorkflowState() || startAutoWorkflow(pkg, { autosave: true }) || {};
  if (isEbayDraftsPage() && workflow.phase === "saving") {
    return finalizeSavedDraftWorkflow(pkg, workflow);
  }
  if (isEbayPrelistPage()) {
    writeAutoWorkflowState({ phase: "prelist", status: "running" });
    const prelistLines = [];
    let prelistResult = null;
    for (let step = 0; step < 6 && isEbayPrelistPage(); step += 1) {
      prelistResult = await prepareEbayPrelist(pkg);
      prelistLines.push(...(prelistResult.lines || []));
      if (!prelistResult.ok || isEbayListingEditorPage()) break;
      await delay(650);
    }
    return {
      lines: prelistLines,
      message: `${prelistResult?.message || "Prepared eBay's pre-list steps."} Auto workflow will continue after eBay opens the next step.`,
      terminal: false,
    };
  }
  if (!isEbayListingEditorPage()) {
    return {
      lines: ["Review eBay page"],
      message: "Auto draft workflow is waiting for an eBay prelist or listing editor page.",
      terminal: false,
    };
  }

  await waitForEditorReady();
  writeAutoWorkflowState({ phase: "editor", status: "running", draftId: readDraftIdFromUrl() || workflow.draftId || "" });
  const fillResult = await fillEbayListingDraft(pkg, onProgress);
  onProgress(82, "Uploading listing images...");
  const uploadResult = await uploadListingImages(pkg);
  onProgress(94, "Running final listing checks...");
  await finishListingEditorView();
  const filledEnough = fillResult.filled >= Math.min(4, fillResult.total);
  const lines = [...fillResult.lines, `Images: ${uploadResult.message}`];
  const criticalChecks = criticalListingCheckDetails(pkg);
  const criticalOk = criticalChecks.every((check) => check.ok);
  const draftId = readDraftIdFromUrl();
  const failedCritical = criticalChecks.filter((check) => !check.ok).map((check) => check.label);

  if (currentWorkflowJobId()) {
    await updateListingJob(currentWorkflowJobId(), {
      status: filledEnough && criticalOk && uploadResult.ok ? "ready_to_save" : "needs_review",
      ebay_draft_id: draftId || null,
      message: `Auto workflow filled ${fillResult.filled}/${fillResult.total} field group(s); ${uploadResult.message}.${failedCritical.length ? ` Review: ${failedCritical.join(", ")}.` : ""}`,
    });
  }

  if (!filledEnough || !criticalOk || !uploadResult.ok) {
    writeAutoWorkflowState({ phase: "needs_review", status: "failed", draftId: draftId || "" });
    return {
      lines,
      message: `Manual review needed before saving. Filled ${fillResult.filled}/${fillResult.total}; ${uploadResult.message}.`,
      terminal: true,
    };
  }

  if (workflow.autoSubmit === true && pkg.listing_schedule_at) {
    const submitResult = await submitScheduledListing(pkg);
    lines.push(submitResult.ok ? "OK submitted scheduled listing" : "Review scheduled listing submission");
    if (!submitResult.ok) {
      if (currentWorkflowJobId()) {
        await updateListingJob(currentWorkflowJobId(), {
          status: "needs_review",
          message: submitResult.message,
        });
      }
      writeAutoWorkflowState({ phase: "needs_review", status: "failed", draftId: draftId || "" });
      return { lines, message: submitResult.message, terminal: true };
    }
    writeAutoWorkflowState({ phase: "submitting", status: "running", draftId: draftId || "" });
    if (currentWorkflowJobId()) {
      await updateListingJob(currentWorkflowJobId(), {
        status: "running",
        ebay_draft_id: draftId || null,
        message: "Submitted the scheduled listing to eBay; waiting for confirmation.",
      });
    }
    const confirmed = await waitForCondition(() => Boolean(detectEbayPublishConfirmation()), 20000, 500);
    if (confirmed) {
      const confirmation = await reportEbayPublishConfirmation();
      return {
        lines,
        message: confirmation?.message || "eBay confirmed the scheduled listing.",
        terminal: true,
      };
    }
    const postSubmitIssue = detectEbaySubmissionIssue();
    if (postSubmitIssue && currentWorkflowJobId()) {
      await updateListingJob(currentWorkflowJobId(), { status: "needs_review", message: postSubmitIssue });
      writeAutoWorkflowState({ phase: "needs_review", status: "failed", draftId: draftId || "" });
    }
    return {
      lines,
      message: postSubmitIssue || "Schedule was submitted. Waiting for eBay confirmation; do not submit it again.",
      terminal: false,
    };
  }

  if (workflow.autosave !== false) {
    const saveResult = await saveDraftForLater();
    lines.push(saveResult.ok ? "OK clicked Save for later" : "Review Save for later");
    if (!saveResult.ok) {
      writeAutoWorkflowState({ phase: "ready_to_save", status: "failed", draftId: draftId || "" });
      return {
        lines,
        message: `${saveResult.message}. Filled ${fillResult.filled}/${fillResult.total}; ${uploadResult.message}.`,
        terminal: true,
      };
    }
    writeAutoWorkflowState({ phase: "saving", status: "running", draftId: draftId || "" });
    await waitForCondition(() => isEbayDraftsPage(), 12000);
    const savedWorkflow = readAutoWorkflowState() || {};
    if (isEbayDraftsPage()) {
      return finalizeSavedDraftWorkflow(pkg, savedWorkflow);
    }
    return {
      lines,
      message: "Clicked Save for later. Waiting for eBay to show Manage drafts.",
      terminal: false,
    };
  }

  return {
    lines,
    message: `Ready to save manually. Filled ${fillResult.filled}/${fillResult.total}; ${uploadResult.message}.`,
    terminal: true,
  };
}

function criticalListingCheckDetails(pkg) {
  const expectedImages = Math.min(24, [...new Set(pkg.manual_image_paths || pkg.local_image_paths || [])].filter(Boolean).length);
  const checks = [
    { label: "title", ok: fieldMatchesHints(["title", "listing title"], pkg.title, { exact: true }) },
    { label: "price", ok: fieldMatchesHints(["price", "buy it now", "fixed price"], Number(pkg.price).toFixed(2), { exact: true }) },
    { label: "description", ok: descriptionSourceMatches(pkg.description) },
    { label: "required item specifics", ok: requiredItemSpecificsSatisfied() },
    { label: "photos", ok: expectedImages > 0 && readEbayPhotoUploadCount() >= expectedImages },
  ];
  if (pkg.listing_schedule_at) {
    const schedule = parseListingSchedule(pkg.listing_schedule_at);
    checks.push({ label: "schedule date", ok: Boolean(schedule && scheduleDateFieldMatches(findScheduleDayField(), schedule)) });
    checks.push({ label: "schedule time", ok: Boolean(schedule && scheduleTimeMatches(schedule)) });
  }
  if (pkg.offers_enabled === false) checks.push({ label: "offers disabled", ok: offersAreDisabled() });
  if (pkg.shipping_cost_type === "flat" || Number(pkg.buyer_shipping_cost) === 0) {
    checks.push({ label: "free flat shipping", ok: flatShippingVisible() && shippingCostReadsAsZero() });
  }
  return checks;
}

function criticalListingChecksPassed(pkg) {
  return criticalListingCheckDetails(pkg).every((check) => check.ok);
}

function fieldMatchesHints(hints, value, options = {}) {
  const expected = String(value ?? "");
  if (!expected) return false;
  const normalizedHints = hints.map(normalizeText);
  return candidateFields()
    .filter((field) => normalizedHints.some((hint) => field.haystack.includes(hint)))
    .some((field) => options.exact ? fieldValueMatchesExactly(field.element, expected) : fieldContainsValue(field.element, expected));
}

function descriptionSourceMatches(value) {
  const html = String(value || "");
  if (!html) return false;
  const hiddenDescription = document.querySelector('textarea[name="description"]');
  if (hiddenDescription && fieldContainsValue(hiddenDescription, html)) return true;
  const htmlEnabled = Boolean(findHtmlCodeCheckbox()?.checked);
  if (!htmlEnabled) return false;
  return candidateFields()
    .filter((field) => /description|html|source|code/.test(field.haystack))
    .some((field) => fieldContainsValue(field.element, html));
}

function offersAreDisabled() {
  const offerControls = [...document.querySelectorAll('input[type="checkbox"], input[type="radio"]')]
    .filter(isVisible)
    .filter((element) => /bestoffer|allowoffers|makeoffer/.test(normalizeText(`${element.getAttribute("aria-label") || ""} ${labelText(element)} ${nearbyText(element)}`)));
  return !offerControls.some((element) => element.checked);
}

function itemSpecificMatches(key, value) {
  const expectedKey = normalizeText(key);
  const expectedValue = normalizeComparableValue(value);
  if (!expectedKey || !expectedValue) return false;
  const controls = [...document.querySelectorAll('button[name^="attributes."], input, textarea')].filter(isVisible);
  return controls.some((element) => {
    const label = normalizeText(`${element.getAttribute("name") || ""} ${element.getAttribute("aria-label") || ""} ${nearbyText(element)}`);
    const current = normalizeComparableValue(element.value || element.innerText || element.textContent || "");
    return label.includes(expectedKey) && (current.includes(expectedValue) || expectedValue.includes(current));
  });
}

async function finalizeSavedDraftWorkflow(pkg, workflow) {
  const draftId = workflow.draftId || readDraftIdFromUrl() || "";
  const title = String(pkg.title || "").trim();
  const draftVisible = !title || (document.body?.innerText || "").includes(title);
  const lines = [
    draftVisible ? "OK saved draft visible" : "Review saved draft visibility",
    draftId ? `OK draft id ${draftId}` : "Review draft id",
  ];
  if (currentWorkflowJobId()) {
    await updateListingJob(currentWorkflowJobId(), {
      status: "saved_draft",
      ebay_draft_id: draftId || null,
      message: draftVisible ? "Saved for later on eBay by AutoZS workflow" : "Save for later clicked; verify draft in eBay",
    });
  }
  writeAutoWorkflowState({ phase: "completed", status: "completed", draftId });
  return {
    lines,
    message: draftVisible ? "Saved for later. Draft is visible in eBay Manage drafts." : "Saved for later. Verify the draft in eBay Manage drafts.",
    terminal: true,
  };
}

function currentWorkflowJobId() {
  const workflow = readAutoWorkflowState();
  return workflow?.jobId || readSavedJobId() || "";
}

function currentWorkflowAccountKey() {
  const params = readAutozsParams();
  const workflow = readAutoWorkflowState();
  return params.get("autozs_account_key") || workflow?.accountKey || "manual";
}

function readDraftIdFromUrl() {
  try {
    return new URLSearchParams(location.search).get("draftId") || "";
  } catch {
    return "";
  }
}

function isEbayDraftsPage() {
  return /(^|\.)ebay\.com$/i.test(location.hostname) && /^\/sh\/lst\/drafts\b/i.test(location.pathname);
}

function detectEbaySubmissionIssue() {
  const text = String(document.body?.innerText || "").replace(/\s+/g, " ").trim();
  const blockingPatterns = [
    /captcha/i,
    /verify (?:your )?(?:identity|account|phone)/i,
    /security (?:check|verification)/i,
    /confirm (?:your )?(?:identity|account)/i,
    /unusual activity/i,
    /we (?:ran into|encountered) a problem/i,
    /listing (?:cannot|could not|can'?t) be (?:submitted|scheduled|listed)/i,
  ];
  const blocking = blockingPatterns.find((pattern) => pattern.test(text));
  if (blocking) return "eBay requires verification or reported a blocking error. AutoZS did not continue.";
  const visibleErrors = [...document.querySelectorAll('[role="alert"], [aria-live="assertive"], .error, [class*="error" i]')]
    .filter(isVisible)
    .map((element) => String(element.innerText || element.textContent || "").replace(/\s+/g, " ").trim())
    .filter((value) => value && /required|invalid|error|fix|unable|cannot|could not|problem/i.test(value));
  return visibleErrors.length ? `eBay needs review: ${visibleErrors.slice(0, 2).join(" | ")}` : "";
}

function findFinalScheduleButton() {
  const candidates = [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .filter((element) => !element.disabled && element.getAttribute("aria-disabled") !== "true")
    .map((element) => ({
      element,
      label: String(element.innerText || element.textContent || element.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim(),
    }));
  const exactPatterns = [
    /^schedule (?:your )?listing$/i,
    /^list for free$/i,
    /^list it$/i,
    /^publish listing$/i,
  ];
  for (const pattern of exactPatterns) {
    const match = candidates.find((candidate) => pattern.test(candidate.label));
    if (match) return match.element;
  }
  return null;
}

async function submitScheduledListing(pkg) {
  if (!pkg.listing_schedule_at) return { ok: false, message: "A scheduled start is required for automatic submission." };
  const schedule = parseListingSchedule(pkg.listing_schedule_at);
  if (!schedule || !scheduleDateFieldMatches(findScheduleDayField(), schedule)) {
    return { ok: false, message: "The eBay schedule date could not be verified, so AutoZS did not submit." };
  }
  const issue = detectEbaySubmissionIssue();
  if (issue) return { ok: false, message: issue };
  const button = findFinalScheduleButton();
  if (!button) return { ok: false, message: "Could not find eBay's final Schedule/List button. AutoZS did not submit." };
  const clicked = await clickEbayElement(button);
  return clicked
    ? { ok: true, message: "Clicked eBay's final scheduled-listing button." }
    : { ok: false, message: "Could not click eBay's final scheduled-listing button." };
}

async function saveDraftForLater() {
  const button = [...document.querySelectorAll("button")]
    .filter(isVisible)
    .find((element) => /^save for later$/i.test((element.innerText || element.textContent || "").trim()));
  if (!button || typeof button.click !== "function") {
    return { ok: false, message: "Could not find eBay Save for later button" };
  }
  button.click();
  return { ok: true, message: "Clicked Save for later" };
}

async function waitForCondition(predicate, timeoutMs = 10000, intervalMs = 500) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (predicate()) return true;
    await delay(intervalMs);
  }
  return false;
}

async function waitForEditorReady() {
  return waitForCondition(() => {
    const text = document.body?.innerText || "";
    return /PHOTOS|Photo/i.test(text) && /TITLE|Item title/i.test(text) && /PRICING|Item price/i.test(text);
  }, 30000, 750);
}

async function prepareEbayPrelist(pkg) {
  const categoryResult = await preparePrelistCategory();
  if (categoryResult) return categoryResult;

  const matchResult = await continueWithoutCatalogMatch();
  if (matchResult) return matchResult;

  let conditionResult = await preparePrelistCondition(pkg);
  if (conditionResult) return conditionResult;

  const title = String(pkg.title || "").trim();
  let searchInput = findPrelistSearchInput();
  if (!searchInput) {
    await waitForCondition(() => Boolean(findPrelistSearchInput()) || Boolean(document.querySelector('input[type="radio"], [role="radio"]')), 5000, 250);
    conditionResult = await preparePrelistCondition(pkg);
    if (conditionResult) return conditionResult;
    searchInput = findPrelistSearchInput();
  }
  if (!title) {
    return { ok: false, lines: ["Review prelist title"], message: "Product title is missing, so the eBay prelist search was not filled." };
  }
  if (!searchInput) {
    return { ok: false, lines: ["Review prelist search input"], message: "Could not find the eBay start-listing search field." };
  }
  await setEbayTextFieldValue(searchInput, title);
  if (!fieldContainsValue(searchInput, title)) {
    return { ok: false, lines: ["Review prelist title"], message: "eBay did not retain the prelist search title." };
  }
  await delay(350);
  const searchButton = findPrelistSearchButton();
  if (searchButton) {
    const searchPageUrl = location.href;
    const searchAdvanced = await clickPrelistElementAndWait(searchButton, () => {
      return location.href !== searchPageUrl || !findPrelistSearchInput() || /find a match|related listings from other sellers/i.test(document.body?.innerText || "");
    });
    if (!searchAdvanced) {
      return { ok: false, lines: [`OK prelist search: ${title}`, "Review Search button"], message: "eBay did not advance after AutoZS clicked Search." };
    }
    const conditionAfterSearch = await preparePrelistCondition(pkg);
    if (conditionAfterSearch?.ok) {
      return {
        ok: true,
        lines: [`OK prelist search: ${title}`, "OK clicked Search", ...conditionAfterSearch.lines],
        message: conditionAfterSearch.message,
      };
    }
    return { ok: true, lines: [`OK prelist search: ${title}`, "OK clicked Search"], message: "Started eBay listing search with the product title." };
  }
  return { ok: true, lines: [`OK prelist search: ${title}`, "Review Search button"], message: "Filled eBay listing search with the product title." };
}

async function continueWithoutCatalogMatch() {
  const pageText = document.body?.innerText || "";
  if (!/find a match|related listings from other sellers/i.test(pageText)) return null;
  const button = [...document.querySelectorAll("button, a")]
    .filter(isVisible)
    .find((element) => /^continue without match$/i.test((element.innerText || element.textContent || "").trim()));
  if (!button) {
    return {
      ok: false,
      lines: ["Review Continue without match"],
      message: "eBay is asking for a catalog match. Click Continue without match to keep importing.",
    };
  }
  const pageUrl = location.href;
  const clicked = await clickPrelistElementAndWait(button, () => {
    const stillVisible = [...document.querySelectorAll("button, a")]
      .filter(isVisible)
      .some((element) => /^continue without match$/i.test((element.innerText || element.textContent || "").trim()));
    return location.href !== pageUrl || !stillVisible || isEbayListingEditorPage() || /condition/i.test(document.body?.innerText || "");
  });
  return {
    ok: Boolean(clicked),
    lines: [`${clicked ? "OK" : "Review"} clicked Continue without match`],
    message: clicked ? "Skipped eBay catalog match and continued the import workflow." : "Could not click Continue without match.",
  };
}

async function preparePrelistCondition(pkg) {
  const pageText = document.body?.innerText || "";
  if (!/condition/i.test(pageText) || !/(new|used|open box|refurbished)/i.test(pageText)) return null;

  const condition = String(pkg.condition || "New").trim() || "New";
  const conditionOk = await chooseVisibleCondition(condition);
  const continueOk = conditionOk ? await clickPrelistContinueButton() : false;
  return {
    ok: conditionOk && continueOk,
    lines: [`${conditionOk ? "OK" : "Review"} condition: ${condition}`, `${continueOk ? "OK" : "Review"} clicked Continue to listing`],
    message: continueOk ? `Selected ${condition} and continued to the listing editor.` : `Select ${condition}, then continue to the listing editor.`,
  };
}

async function chooseVisibleCondition(condition) {
  const normalized = normalizeText(condition);
  const controls = conditionControls()
    .filter(isVisible)
    .map((element) => ({
      element,
      text: normalizeText(
        [
          element.value,
          element.getAttribute("aria-label"),
          labelText(element),
          nearbyText(element),
          element.innerText,
          element.textContent,
        ]
          .filter(Boolean)
          .join(" ")
      ),
    }));
  let match = controls.find((control) => conditionControlMatches(control, normalized));
  if (!match) {
    const opener = controls.find((control) => /condition/.test(control.text) && /select|choose|condition|new|used|openbox|refurbished/.test(control.text));
    if (opener) {
      await clickEbayElement(opener.element);
      await delay(350);
      const popupControls = conditionPopupControls()
        .filter(isVisible)
        .map((element) => ({
          element,
          text: normalizeText(
            [
              element.value,
              element.getAttribute("aria-label"),
              labelText(element),
              nearbyText(element),
              element.innerText,
              element.textContent,
            ]
              .filter(Boolean)
              .join(" ")
          ),
        }));
      match = popupControls.find((control) => conditionControlMatches(control, normalized));
    }
  }
  if (!match) return conditionSelectionMatches(condition);
  if (match.element.matches?.('input[type="radio"]')) {
    if (match.element.checked) return conditionSelectionMatches(condition);
    const clicked = await clickConditionChoice(match.element);
    if (!clicked) return false;
    match.element.dispatchEvent(new Event("input", { bubbles: true }));
    match.element.dispatchEvent(new Event("change", { bubbles: true }));
    await delay(350);
    return match.element.checked || conditionSelectionMatches(condition) || conditionContinueButtonEnabled();
  }
  await clickConditionChoice(match.element);
  await delay(350);
  return conditionSelectionMatches(condition) || conditionContinueButtonEnabled();
}

function conditionControls() {
  return [...document.querySelectorAll('input[type="radio"], button, [role="button"], [role="radio"], [role="combobox"], label')];
}

function conditionPopupControls() {
  const popups = [...document.querySelectorAll('[role="dialog"], [role="listbox"], [role="menu"], [data-testid*="condition" i]')].filter(isVisible);
  const scoped = popups.flatMap((popup) => [...popup.querySelectorAll?.('input[type="radio"], button, [role="button"], [role="radio"], [role="option"], [role="menuitem"], label, li') || []]);
  return [...scoped, ...document.querySelectorAll('input[type="radio"], button, [role="button"], [role="radio"], [role="option"], [role="menuitem"], label, li')];
}

function conditionControlMatches(control, normalizedCondition) {
  if (!control?.text || !normalizedCondition) return false;
  const exactText = normalizeText(control.element?.innerText || control.element?.textContent || control.element?.value || control.element?.getAttribute?.("aria-label") || "");
  return exactText === normalizedCondition || control.text === normalizedCondition || control.text.includes(`condition${normalizedCondition}`) || control.text.includes(normalizedCondition);
}

async function clickConditionChoice(element) {
  const label = conditionAssociatedLabel(element);
  if (label && isVisible(label) && await clickEbayElement(label)) return true;
  const row = element?.closest?.(".radio, .field, li, div");
  if (row && row !== element && isVisible(row) && /new|open box|used|for parts|not working|refurbished/i.test(row.innerText || row.textContent || "")) {
    if (await clickEbayElement(row)) return true;
  }
  return clickEbayElement(element);
}

function conditionAssociatedLabel(element) {
  if (!element) return null;
  if (element.id) {
    const direct = document.querySelector(`label[for="${cssEscape(element.id)}"]`);
    if (direct) return direct;
  }
  return element.closest?.("label") || null;
}

function conditionSelectionMatches(condition) {
  const normalized = normalizeText(condition);
  if (!normalized) return false;
  const selected = [...document.querySelectorAll('input[type="radio"]:checked, [aria-checked="true"], [aria-selected="true"]')]
    .filter(isVisible)
    .some((element) => normalizeText(`${element.value || ""} ${element.getAttribute?.("aria-label") || ""} ${labelText(element)} ${nearbyText(element)} ${element.innerText || ""} ${element.textContent || ""}`).includes(normalized));
  if (selected) return true;
  return conditionControls().filter(isVisible).some((element) => {
    const text = normalizeText(`${element.getAttribute?.("aria-label") || ""} ${element.innerText || ""} ${element.textContent || ""} ${nearbyText(element)}`);
    return text.includes("condition") && text.includes(normalized) && !/select|choose|required/.test(text);
  });
}

function conditionContinueButtonEnabled() {
  return [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .some((button) => /^(continue|continue to listing|next)$/i.test((button.innerText || button.textContent || "").trim()) && !button.disabled && button.getAttribute("aria-disabled") !== "true");
}

async function clickPrelistContinueButton() {
  const button = [...document.querySelectorAll("button, a")]
    .filter(isVisible)
    .find((element) => /^(continue|continue to listing|next)$/i.test((element.innerText || element.textContent || "").trim()));
  if (!button || typeof button.click !== "function") return false;
  const pageUrl = location.href;
  return clickPrelistElementAndWait(button, () => {
    return location.href !== pageUrl || isEbayListingEditorPage() || !isVisible(button);
  });
}

function requiredItemSpecificsSatisfied() {
  const text = document.body?.innerText || "";
  return !/additional details are required|item specific\s+[^.\n]+\s+is missing/i.test(text);
}

async function preparePrelistCategory() {
  const pageText = document.body?.innerText || "";
  if (!/provide a category for your item|select a category/i.test(pageText)) return null;
  const dialog = document.querySelector('[role="dialog"]') || document;
  const categoryButton = [...dialog.querySelectorAll("button")]
    .filter(isVisible)
    .find((button) => /\s>\s/.test((button.innerText || button.textContent || "").trim()));
  if (!categoryButton) {
    return { ok: false, lines: ["Review suggested category"], message: "eBay needs a category, but AutoZS could not find a suggested category." };
  }
  const categorySelected = await clickPrelistElementAndWait(categoryButton, () => {
    const text = document.body?.innerText || "";
    return !/none selected/i.test(text) || !/provide a category for your item/i.test(text);
  }, 3000);
  if (categorySelected && !/provide a category for your item/i.test(document.body?.innerText || "")) {
    return { ok: true, lines: ["OK selected first suggested category"], message: "Selected eBay's first suggested category and continued." };
  }
  const doneButton = [...dialog.querySelectorAll("button")]
    .filter(isVisible)
    .find((button) => /^done$/i.test((button.innerText || button.textContent || "").trim()));
  if (!doneButton) {
    return { ok: false, lines: ["OK selected first suggested category", "Review category Done button"], message: "Selected eBay's first suggested category, but could not find Done." };
  }
  const pageUrl = location.href;
  const completed = await clickPrelistElementAndWait(doneButton, () => {
    return location.href !== pageUrl || !/provide a category for your item/i.test(document.body?.innerText || "");
  });
  return {
    ok: completed,
    lines: ["OK selected first suggested category", `${completed ? "OK" : "Review"} confirmed category`],
    message: completed ? "Selected eBay's first suggested category and continued." : "Selected a suggested category, but eBay did not continue after Done.",
  };
}

async function clickPrelistElementAndWait(element, advanced, timeoutMs = 5000) {
  if (!element || typeof element.click !== "function") return false;
  element.scrollIntoView?.({ block: "center", inline: "center" });
  element.click();
  if (await waitForCondition(advanced, timeoutMs, 150)) return true;
  const nativeClicked = await clickEbayElement(element);
  return Boolean(nativeClicked && (await waitForCondition(advanced, timeoutMs, 150)));
}

function findPrelistSearchInput() {
  const fields = [...document.querySelectorAll("input, textarea, [role='textbox']")].filter(isVisible);
  return (
    fields.find((element) => /enter brand, model, description/i.test(element.getAttribute("placeholder") || element.getAttribute("aria-label") || "")) ||
    fields.find((element) => {
      const parent = element.closest("form, section, div");
      return /start listing with item info|describe your item/i.test(parent?.innerText || "");
    }) ||
    null
  );
}

function findPrelistSearchButton() {
  return [...document.querySelectorAll("button")].filter(isVisible).find((button) => /^search$/i.test((button.innerText || button.textContent || "").trim())) || null;
}

function fillByHints(hints, value) {
  const normalizedHints = hints.map(normalizeText);
  const fields = candidateFields();
  const match = fields.find((field) => normalizedHints.some((hint) => field.haystack.includes(hint)));
  if (!match) return false;
  return setFieldValue(match.element, value);
}

async function fillEbayFieldByHints(hints, value) {
  const normalizedHints = hints.map(normalizeText);
  const match = candidateFields().find((field) => normalizedHints.some((hint) => field.haystack.includes(hint)));
  return match ? setEbayTextFieldValue(match.element, value) : false;
}

async function fillEbayItemSpecific(key, value) {
  if (await fillEbayFieldByHints([key], value)) return true;
  if (await fillEbayItemSpecificDropdown(key, value)) return true;
  return suggestedItemSpecificMatches(key, value);
}

async function fillEbayItemSpecificDropdown(key, value) {
  const normalizedKey = normalizeText(key);
  const expected = String(value ?? "").trim();
  if (!normalizedKey || !expected) return false;
  const controls = [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .map((element) => {
      const text = normalizeText([
        element.id,
        element.name,
        element.getAttribute("aria-label"),
        element.getAttribute("data-testid"),
        element.innerText,
        element.textContent,
        labelText(element),
        nearbyText(element),
      ].filter(Boolean).join(" "));
      return { element, text };
    });
  const trigger =
    controls.find((control) => control.text.includes(`attributes${normalizedKey}`))?.element ||
    controls.find((control) => control.text.includes(normalizedKey))?.element ||
    null;
  if (!trigger) return false;
  const currentText = normalizeComparableValue(`${trigger.innerText || trigger.textContent || ""} ${nearbyText(trigger)}`);
  const expectedComparable = normalizeComparableValue(expected);
  const binaryChoicesVisible = /^(yes|no)$/.test(expectedComparable) && currentText.includes("yes") && currentText.includes("no");
  if (!binaryChoicesVisible && currentText.includes(expectedComparable)) return true;
  await clickEbayElement(trigger);
  await delay(350);

  const input =
    [...document.querySelectorAll("input, [role='textbox']")]
      .filter(isVisible)
      .find((element) => {
        const text = normalizeText([element.id, element.name, element.getAttribute("aria-label"), element.getAttribute("placeholder"), nearbyText(element)].filter(Boolean).join(" "));
        return text.includes(normalizedKey) || /searchorenteryourown|searchresultsappearbelow/.test(text);
      }) ||
    [...document.querySelectorAll("input, [role='textbox']")]
      .filter(isVisible)
      .find((element) => /search/i.test(`${element.getAttribute("aria-label") || ""} ${element.getAttribute("placeholder") || ""}`));
  if (input) {
    await setEbayTextFieldValue(input, expected);
    await delay(500);
  }

  const option = [...document.querySelectorAll("[role='option'], [role='menuitem'], button, li, div")]
    .filter(isVisible)
    .find((element) => normalizeComparableValue(element.innerText || element.textContent || "") === normalizeComparableValue(expected));
  if (option) {
    await clickEbayElement(option);
    await delay(500);
  } else if (input) {
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
    await delay(500);
  }

  const updatedText = normalizeComparableValue(document.body?.innerText || "");
  return updatedText.includes(normalizeComparableValue(expected)) || itemSpecificMatches(key, expected);
}

function inferredItemSpecifics(pkg) {
  const specifics = { ...(pkg.item_specifics || {}) };
  const title = String(pkg.title || "");
  const description = stripListingHtml(pkg.description || "");
  const source = `${title} ${description}`;
  if (!specifics["Battery Included"] && /\bbatter(?:y|ies)\b/i.test(source)) specifics["Battery Included"] = "Yes";
  if (!specifics.Voltage) {
    const voltage = source.match(/\b(\d{1,3})\s*[- ]?\s*v(?:olt)?\b/i);
    if (voltage) specifics.Voltage = `${voltage[1]} V`;
  }
  return specifics;
}

async function fillDescription(value) {
  const htmlValue = String(value || "");
  const isHtmlDescription = looksLikeHtml(htmlValue);
  if (isHtmlDescription && await fillDescriptionHtmlSource(htmlValue)) return true;
  const text = listingDescriptionPlainText(htmlValue);
  if (await fillDescriptionNativeFrame(htmlValue)) return true;
  if (await fillDescriptionHtmlSource(htmlValue)) return true;
  const directDescription = [...document.querySelectorAll("textarea, [contenteditable], [role='textbox']")]
    .filter(isVisible)
    .find((element) =>
      /description|item description/i.test(
        [
          element.getAttribute("aria-label"),
          element.getAttribute("aria-placeholder"),
          element.getAttribute("data-placeholder"),
          element.getAttribute("placeholder"),
          labelText(element),
          nearbyText(element),
        ]
          .filter(Boolean)
          .join(" ")
      )
    );
  if (directDescription) {
    if (isRichTextElement(directDescription)) {
      if (setRichTextValue(directDescription, htmlValue)) {
        await delay(350);
        if (fieldContainsValue(directDescription, text)) return true;
      }
    } else if (setFieldValue(directDescription, text)) {
      await delay(350);
      if (fieldContainsValue(directDescription, text)) return true;
    }
  }
  if (fillByHints(["description", "item description"], text)) {
    await delay(350);
    const matchingField = candidateFields().find((field) => field.haystack.includes("description"));
    if (matchingField && fieldContainsValue(matchingField.element, text)) return true;
  }
  const editable = [...document.querySelectorAll("[contenteditable], [role='textbox']")].find((element) => isVisible(element));
  if (editable) {
    if (setRichTextValue(editable, htmlValue)) {
      await delay(350);
      if (fieldContainsValue(editable, text)) return true;
    }
  }
  for (const frame of document.querySelectorAll("iframe")) {
    try {
      const frameDocument = frame.contentDocument;
      const body = frameDocument?.body;
      if (!body || !frameDocument) continue;
      body.focus();
      const inserted = frameDocument.execCommand("selectAll", false) && frameDocument.execCommand("insertHTML", false, htmlValue);
      if (!inserted) body.innerHTML = htmlValue;
      body.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "insertHTML", data: htmlValue }));
      body.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertHTML", data: htmlValue }));
      body.dispatchEvent(new Event("change", { bubbles: true }));
      body.dispatchEvent(new Event("blur", { bubbles: true }));
      await delay(500);
      if (normalizeComparableValue(body.innerText).includes(normalizeComparableValue(text).slice(0, 80))) return true;
    } catch {}
  }
  return false;
}

async function fillDescriptionNativeFrame(htmlValue) {
  const text = listingDescriptionPlainText(htmlValue);
  if (!text.trim()) return false;
  const frame = document.querySelector('iframe[aria-label*="Description" i], iframe[name="se-rte-frame__summary"], iframe#se-rte-frame__summary');
  if (!frame) return false;
  try {
    frame.scrollIntoView?.({ block: "center", inline: "center" });
    await delay(200);
    const rect = frame.getBoundingClientRect();
    const targetX = rect.left + Math.max(20, Math.min(rect.width / 2, rect.width - 20));
    const targetY = rect.top + Math.max(20, Math.min(rect.height / 2, rect.height - 20));
    const inViewport = targetX >= 0 && targetY >= 0 && targetX <= window.innerWidth && targetY <= window.innerHeight;
    if (!rect.width || !rect.height || !inViewport) return false;
    const focused = await requestNativeEbayInput({ action: "click", x: targetX, y: targetY });
    if (!focused) return false;
    await delay(200);
    const typed = await requestNativeEbayInput({ action: "replace-text", text });
    await delay(600);
    return Boolean(typed);
  } catch {
    return false;
  }
}

async function fillDescriptionHtmlSource(htmlValue) {
  if (!htmlValue.trim()) return false;
  const htmlMode = await enableHtmlCodeMode();
  if (!htmlMode) return false;

  const sourceField = await waitForDescriptionSourceField();
  if (!sourceField) return false;
  if (!isVisible(sourceField.element)) return false;

  await replaceDescriptionSourceNativeFirst(sourceField.element, htmlValue);
  sourceField.element.blur?.();
  await delay(450);
  if (!descriptionSourceExactlyMatches(sourceField.element, htmlValue)) {
    if (isVisible(sourceField.element)) await replaceDescriptionSourceNativeFirst(sourceField.element, htmlValue);
    else replaceDescriptionSourceValue(sourceField.element, htmlValue);
    await delay(250);
  }
  if (!descriptionSourceExactlyMatches(sourceField.element, htmlValue)) {
    replaceDescriptionSourceValue(sourceField.element, htmlValue);
    await delay(250);
  }
  return descriptionSourceExactlyMatches(sourceField.element, htmlValue);
}

async function enableHtmlCodeMode() {
  const existingField = findDescriptionSourceField();
  if (existingField && isVisible(existingField.element)) return true;

  const checkbox = findHtmlCodeCheckbox();
  if (checkbox) {
    if (checkbox.checked && !visibleDescriptionSourceField()) {
      checkbox.click();
      await delay(300);
    }
    if (!checkbox.checked || !visibleDescriptionSourceField()) {
      const label = findHtmlCodeLabel(checkbox) || checkbox.closest?.("label");
      (label || checkbox).click();
      await waitForCondition(() => Boolean(visibleDescriptionSourceField()), 4500, 100);
    }
    if (visibleDescriptionSourceField()) return true;
  }

  const control = findHtmlCodeControl();
  if (!control) return false;
  await clickHtmlCodeCheckbox(findHtmlCodeCheckboxNear(control) || findHtmlCodeCheckbox() || control);
  return waitForCondition(() => {
    return Boolean(visibleDescriptionSourceField());
  }, 4500, 100);
}

function visibleDescriptionSourceField() {
  const field = findDescriptionSourceField();
  return field && isVisible(field.element) ? field : null;
}

async function clickHtmlCodeCheckbox(target) {
  if (!target) return false;
  const clickable = target.matches?.('input[type="checkbox"]')
    ? target
    : findHtmlCodeCheckboxNear(target) || findHtmlCodeCheckbox() || target;
  const targets = [
    clickable,
    findHtmlCodeLabel(clickable),
    clickable?.closest?.("label"),
    clickable?.parentElement,
    target,
    target?.parentElement,
  ].filter(Boolean);
  for (const item of targets) {
    item.click?.();
    await delay(250);
    if (visibleDescriptionSourceField()) return true;
  }
  const checkbox = findHtmlCodeCheckbox();
  if (checkbox && !checkbox.checked) {
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("input", { bubbles: true }));
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    await delay(300);
  }
  return Boolean(visibleDescriptionSourceField());
}

async function waitForDescriptionSourceField() {
  let sourceField = findDescriptionSourceField();
  if (sourceField) return sourceField;
  await waitForCondition(() => Boolean(findDescriptionSourceField()), 5000, 150);
  sourceField = findDescriptionSourceField();
  return sourceField || null;
}

function findDescriptionSourceField() {
  const rawDescription = document.querySelector(
    'textarea[name="description"][id*="rawEditor"], textarea[id*="rawEditor"], textarea[name="description"][aria-label*="HTML" i], textarea[name="description"]'
  ) || document.querySelector('textarea[name="description"][id*="rawEditor"], textarea[name="description"]');
  const htmlModeEnabled = descriptionHtmlModeIsEnabled();
  if (rawDescription && (htmlModeEnabled || (isVisible(rawDescription) && descriptionFieldLooksLikeHtmlSource(rawDescription)))) {
    return { element: rawDescription, forceSynthetic: false };
  }
  const sourceField = candidateFields().find((field) => {
    const haystack = field.haystack;
    const element = field.element;
    const editorLike = element?.tagName === "TEXTAREA" || Boolean(element?.isContentEditable);
    return editorLike && /html|source|code/.test(haystack) && /description|raweditor/.test(haystack);
  });
  if (sourceField) return sourceField;
  if (!descriptionHtmlModeIsEnabled()) return null;
  const visibleDescriptionTextarea = [...document.querySelectorAll("textarea")]
    .filter(isVisible)
    .find((element) => /description|write a detailed description|html|source|code/i.test(`${element.placeholder || ""} ${labelText(element)} ${nearbyText(element)}`));
  return visibleDescriptionTextarea ? { element: visibleDescriptionTextarea, forceSynthetic: false } : null;
}

function descriptionHtmlModeIsEnabled() {
  const checkbox = findHtmlCodeCheckbox();
  return Boolean(checkbox?.checked);
}

function descriptionFieldLooksLikeHtmlSource(element) {
  const haystack = normalizeText(
    [
      element?.id,
      element?.name,
      element?.getAttribute?.("aria-label"),
      element?.getAttribute?.("data-testid"),
      labelText(element),
      nearbyText(element),
    ]
      .filter(Boolean)
      .join(" ")
  );
  return /raweditor|html|source|code/.test(haystack);
}

async function replaceDescriptionSourceNativeFirst(element, value) {
  const text = String(value ?? "");
  if (!text.trim()) return false;
  if (!element || !isVisible(element)) return false;
  try {
    const nativeInput = await withEbayAssistantHidden(async () => {
      const focused = await focusTextFieldForNativeReplacement(element);
      if (!focused) return false;
      return requestNativeEbayInput({ action: "replace-text", text });
    });
    await delay(450);
    element.blur?.();
    await delay(250);
    if (nativeInput && descriptionSourceExactlyMatches(element, text)) return true;
  } catch {}
  await replaceVisibleDescriptionSourceValue(element, text);
  element.blur?.();
  await delay(350);
  if (descriptionSourceExactlyMatches(element, text)) return true;
  await setEbayTextFieldValue(element, text);
  element.blur?.();
  await delay(350);
  return descriptionSourceExactlyMatches(element, text);
}

async function replaceVisibleDescriptionSourceValue(element, value) {
  const text = String(value ?? "");
  try {
    element.scrollIntoView?.({ block: "center", inline: "center" });
    await delay(150);
    element.focus?.();
    if (typeof element.select === "function") element.select();
    if (typeof element.setSelectionRange === "function") element.setSelectionRange(0, String(element.value || "").length);
    const inserted = document.execCommand?.("insertText", false, text);
    element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertReplacementText", data: text }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    await delay(250);
    if (inserted && descriptionSourceExactlyMatches(element, text)) return true;
  } catch {}
  replaceDescriptionSourceValue(element, text);
  await delay(250);
  return descriptionSourceExactlyMatches(element, text);
}

function replaceDescriptionSourceValue(element, value) {
  const text = String(value ?? "");
  element.focus?.();
  const prototype = element.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  if (descriptor?.set) descriptor.set.call(element, "");
  else element.value = "";
  element.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "deleteContentBackward", data: null }));
  element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward", data: null }));
  if (descriptor?.set) descriptor.set.call(element, text);
  else element.value = text;
  element.setAttribute?.("value", text);
  element.dispatchEvent(new Event("focus", { bubbles: true }));
  element.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "insertReplacementText", data: text }));
  element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertReplacementText", data: text }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true }));
  return descriptionSourceExactlyMatches(element, text);
}

function descriptionSourceExactlyMatches(element, value) {
  const current = String(element?.value || element?.textContent || "").trim();
  const expected = String(value || "").trim();
  return Boolean(expected) && current === expected;
}

function looksLikeHtml(value) {
  return /<[a-z][\s\S]*>/i.test(String(value || ""));
}

function listingDescriptionPlainText(value) {
  const raw = String(value || "");
  if (!looksLikeHtml(raw)) return raw.trim();
  const withBreaks = raw
    .replace(/<\s*br\s*\/?\s*>/gi, "\n")
    .replace(/<\s*\/\s*(p|div|h[1-6]|li|tr|section|article|header|footer|ul|ol|table)\s*>/gi, "\n")
    .replace(/<\s*(p|div|h[1-6]|li|tr|section|article|header|footer|ul|ol|table)(?:\s[^>]*)?>/gi, "\n");
  const container = document.createElement("div");
  container.innerHTML = withBreaks;
  return (container.innerText || container.textContent || withBreaks)
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function findHtmlCodeCheckbox() {
  const label = [...document.querySelectorAll("label")]
    .find((element) => /show html code|html code/i.test(element.innerText || element.textContent || ""));
  if (label?.getAttribute("for")) {
    const input = document.getElementById(label.getAttribute("for"));
    if (input?.matches?.('input[type="checkbox"]')) return input;
  }
  const textControl = findHtmlCodeTextControl();
  const nearby = textControl ? findHtmlCodeCheckboxNear(textControl) : null;
  if (nearby) return nearby;
  return [...document.querySelectorAll('input[type="checkbox"]')]
    .find((element) => /showhtmlcode|htmlcode|descriptioneditormode/.test(normalizeText(`${element.id} ${element.name} ${element.getAttribute("aria-label") || ""} ${labelText(element)}`))) || null;
}

function findHtmlCodeLabel(checkbox) {
  if (checkbox?.id) {
    const label = document.querySelector(`label[for="${cssEscape(checkbox.id)}"]`);
    if (label && isVisible(label)) return label;
  }
  return checkbox?.closest?.("label") || null;
}

function findHtmlCodeControl() {
  const checkbox = findHtmlCodeCheckbox();
  if (checkbox) return findHtmlCodeLabel(checkbox) || checkbox;
  return findHtmlCodeTextControl();
}

function findHtmlCodeTextControl() {
  return [...document.querySelectorAll("label, button, [role='button'], span, div")]
    .filter(isVisible)
    .sort((a, b) => (a.innerText || a.textContent || "").length - (b.innerText || b.textContent || "").length)
    .find((element) => /show\s*html\s*code/i.test(element.innerText || element.textContent || "")) || null;
}

function findHtmlCodeCheckboxNear(anchor) {
  if (!anchor) return null;
  const anchorRect = anchor.getBoundingClientRect?.();
  const checkboxes = [...document.querySelectorAll('input[type="checkbox"]')].filter(isVisible);
  const nested = anchor.querySelector?.('input[type="checkbox"]');
  if (nested && isVisible(nested)) return nested;
  const container = anchor.closest?.("label, div, section, fieldset, form");
  const inContainer = container ? [...container.querySelectorAll('input[type="checkbox"]')].filter(isVisible) : [];
  if (inContainer.length === 1) return inContainer[0];
  if (!anchorRect?.width && !anchorRect?.height) return null;
  return checkboxes
    .map((checkbox) => {
      const rect = checkbox.getBoundingClientRect();
      const dx = Math.abs((rect.left + rect.width / 2) - (anchorRect.left + anchorRect.width / 2));
      const dy = Math.abs((rect.top + rect.height / 2) - (anchorRect.top + anchorRect.height / 2));
      const leftBonus = rect.left <= anchorRect.left ? -40 : 0;
      return { checkbox, score: dx + dy * 3 + leftBonus };
    })
    .filter((item) => item.score < 700)
    .sort((a, b) => a.score - b.score)[0]?.checkbox || null;
}

async function uploadListingImages(pkg) {
  const imagePaths = [...new Set(pkg.manual_image_paths || pkg.local_image_paths || [])].filter(Boolean).slice(0, 24);
  if (!imagePaths.length) return { ok: false, uploaded: 0, attempted: 0, message: "no downloaded local images in package" };

  scrollToPhotosSection();
  await delay(500);
  const input = findImageFileInput();
  if (!input) return { ok: false, uploaded: 0, attempted: imagePaths.length, message: "could not find eBay image file input" };
  const removed = await removeExistingListingImages();

  let files;
  try {
    files = await Promise.all(imagePaths.map(localPathToFile));
  } catch (error) {
    return { ok: false, uploaded: 0, attempted: imagePaths.length, message: `could not prepare local images: ${error.message}` };
  }

  try {
    const dataTransfer = new DataTransfer();
    files.forEach((file) => dataTransfer.items.add(file));
    const beforeCount = readEbayPhotoUploadCount();
    input.files = dataTransfer.files;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const visibleUploaded = await waitForPhotoUploadProgress(beforeCount, files.length);
    const accepted = Math.max(0, visibleUploaded - beforeCount);
    if (accepted > 0) {
      return {
        ok: accepted >= files.length,
        uploaded: accepted,
        attempted: files.length,
        message:
          accepted >= files.length
            ? `${removed ? `replaced ${removed} existing image(s); ` : ""}uploaded ${accepted}/${files.length} image(s)`
            : `${removed ? `replaced ${removed} existing image(s); ` : ""}eBay accepted ${accepted}/${files.length} image(s); review rejected or pending images`,
      };
    }
    return { ok: false, uploaded: 0, attempted: files.length, message: `sent ${files.length} image(s), but eBay did not show uploads yet` };
  } catch (error) {
    return { ok: false, uploaded: 0, attempted: imagePaths.length, message: `eBay image input rejected files: ${error.message}` };
  }
}

function scrollToPhotosSection() {
  const target = [...document.querySelectorAll("h1, h2, h3, section, div")]
    .find((element) => /photos\s*&\s*video|photos and video|photos/i.test((element.innerText || element.textContent || "").trim()));
  if (target?.scrollIntoView) {
    target.scrollIntoView({ block: "center", inline: "nearest" });
  } else {
    window.scrollTo?.(0, 0);
  }
}

async function removeExistingListingImages() {
  let removed = 0;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const before = readEbayPhotoUploadCount();
    if (before <= 0) break;
    const button = findRemoveImageButton();
    if (!button) break;
    await clickEbayElement(button);
    const confirmed = await confirmRemoveImageIfNeeded();
    if (confirmed) await delay(250);
    const changed = await waitForCondition(() => readEbayPhotoUploadCount() < before, 2500, 150);
    if (!changed) break;
    removed += before - readEbayPhotoUploadCount();
  }
  return removed;
}

function findRemoveImageButton() {
  return [...document.querySelectorAll("button, [role='button'], a")]
    .find((element) => {
      const text = normalizeText([
        element.getAttribute("aria-label"),
        element.getAttribute("title"),
        element.innerText,
        element.textContent,
        nearbyText(element),
      ].filter(Boolean).join(" "));
      return /deletephoto\d+|removephoto\d+|(remove|delete).*(photo|image|picture)|photo.*(remove|delete)|image.*(remove|delete)/.test(text);
    }) || null;
}

async function confirmRemoveImageIfNeeded() {
  const button = [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .find((element) => /^(delete|remove|confirm|yes)$/i.test((element.innerText || element.textContent || "").trim()));
  if (!button) return false;
  await clickEbayElement(button);
  return true;
}

function readEbayPhotoUploadCount() {
  const text = document.body?.innerText || "";
  const slashMatch = text.match(/\b([0-9]{1,2})\s*\/\s*25\b/);
  if (slashMatch) return Number(slashMatch[1]);
  const sentenceMatch = text.match(/\b([0-9]{1,2})\s+out of\s+25\s+photos/i);
  return sentenceMatch ? Number(sentenceMatch[1]) : 0;
}

async function waitForPhotoUploadProgress(beforeCount, attempted) {
  const target = beforeCount + attempted;
  let latest = beforeCount;
  for (let index = 0; index < 12; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    latest = readEbayPhotoUploadCount();
    if (latest >= target) return latest;
  }
  return latest;
}

function findImageFileInput() {
  const inputs = [...document.querySelectorAll('input[type="file"]')].filter((input) => {
    const accept = String(input.getAttribute("accept") || "").toLowerCase();
    return input.multiple || accept.includes("image") || accept.includes("heic") || accept.includes("heif");
  });
  return inputs.find((input) => input.multiple) || inputs[0] || null;
}

async function localPathToFile(localPath) {
  const url = localPathToApiUrl(localPath);
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${localPath} returned ${response.status}`);
  const blob = await response.blob();
  const name = String(localPath).split("/").filter(Boolean).pop() || "autozs-image.jpg";
  return new File([blob], name, { type: blob.type || contentTypeForPath(name) });
}

function localPathToApiUrl(localPath) {
  if (/^https?:\/\//i.test(localPath)) return localPath;
  const clean = String(localPath || "").replace(/^\/+/, "");
  return `${API}/${clean}`;
}

function contentTypeForPath(path) {
  const extension = String(path || "").split(".").pop().toLowerCase();
  if (extension === "png") return "image/png";
  if (extension === "webp") return "image/webp";
  if (extension === "gif") return "image/gif";
  return "image/jpeg";
}

function candidateFields() {
  const elements = [...document.querySelectorAll("input, textarea, [contenteditable], [role='textbox']")]
    .filter(isVisible)
    .filter((element) => {
      if (element.tagName !== "INPUT") return true;
      const type = String(element.getAttribute("type") || "text").toLowerCase();
      return !["checkbox", "radio", "hidden", "file", "button", "submit"].includes(type);
    });
  return elements.map((element) => ({
    element,
    haystack: normalizeText(
      [
        element.id,
        element.name,
        element.placeholder,
        element.getAttribute("aria-label"),
        element.getAttribute("aria-placeholder"),
        element.getAttribute("data-placeholder"),
        element.getAttribute("data-testid"),
        element.getAttribute("autocomplete"),
        labelText(element),
        nearbyText(element),
      ]
        .filter(Boolean)
        .join(" ")
    ),
  }));
}

async function applySuggestedItemSpecifics() {
  const buttons = [...document.querySelectorAll("button")].filter(isVisible);
  const applyAll = buttons.find((button) => normalizeText(button.innerText || button.textContent) === "applyall");
  if (!applyAll) return false;
  const clicked = await clickEbayElement(applyAll);
  await delay(800);
  if (!clicked) return false;
  return true;
}

function suggestedItemSpecificMatches(key, value) {
  const expectedKey = normalizeText(key);
  const expectedValue = normalizeText(value);
  if (!expectedKey || !expectedValue) return false;
  return [...document.querySelectorAll('input[name="extracted-attribute-selector"], input[id^="extracted-attribute-selector-"]')]
    .filter((input) => {
      const text = normalizeText(`${input.value || ""} ${nearbyText(input)}`);
      return text.includes(expectedKey) && (text.includes(expectedValue) || expectedValue.includes(text.replace(expectedKey, "")));
    })
    .some(Boolean);
}

async function applyListingSchedule(pkg) {
  const schedule = parseListingSchedule(pkg.listing_schedule_at);
  if (!schedule) return false;
  const enabled = setCheckboxByHints(["schedule your listing", "schedule listing"], true);
  await waitForCondition(() => Boolean(findScheduleDayField()), 6000, 400);
  const timeOk = await setScheduleTimeButtons(schedule);
  await delay(300);
  const dateOk = await setScheduleDate(schedule);
  await delay(500);
  const verifiedDateOk = scheduleDateFieldMatches(findScheduleDayField(), schedule);
  const verifiedTimeOk = scheduleTimeMatches(schedule);
  return Boolean(enabled && timeOk && verifiedDateOk && dateOk && verifiedTimeOk);
}

async function setScheduleDate(schedule) {
  const dateElement = findScheduleDateElement();
  if (!dateElement) return scheduleVisible(schedule.usDate);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const currentDateElement = findScheduleDateElement() || dateElement;
    const calendarDateSet = await chooseScheduleCalendarDate(currentDateElement, schedule);
    if (calendarDateSet && scheduleDateFieldMatches(findScheduleDayField() || currentDateElement, schedule)) return true;
  }

  // Fallback for eBay layouts that do not expose the calendar buttons. This
  // alone is not trusted for autosave because eBay can display a typed date
  // without committing it to the scheduled-listing state.
  const currentDateElement = findScheduleDateElement() || dateElement;
  const value = currentDateElement.type === "date" ? schedule.isoDate : schedule.usDate;
  await setEbayTextFieldValue(currentDateElement, value);
  currentDateElement.dispatchEvent?.(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
  currentDateElement.dispatchEvent?.(new KeyboardEvent("keyup", { bubbles: true, key: "Enter" }));
  currentDateElement.blur?.();
  await delay(250);
  return scheduleDateFieldMatches(findScheduleDayField() || currentDateElement, schedule);
}

async function chooseScheduleCalendarDate(dateField, schedule) {
  const toggle = findScheduleCalendarToggle(dateField);
  if (!toggle && !dateField) return false;
  await clickEbayElement(toggle || dateField);
  await delay(250);

  for (let attempt = 0; attempt < 18; attempt += 1) {
    const target = findScheduleCalendarDay(schedule);
    if (target) {
      await clickEbayElement(target);
      await delay(400);
      return scheduleDateFieldMatches(findScheduleDayField() || dateField, schedule) || scheduleVisible(schedule.usDate);
    }
    const nextMonth = findScheduleCalendarNextMonth();
    if (!nextMonth) return false;
    await clickEbayElement(nextMonth);
    await delay(250);
  }
  return false;
}

function findScheduleCalendarToggle(dateField) {
  const byControls = dateField?.parentElement?.querySelector?.('button[aria-label*="calendar" i], button[title*="calendar" i]');
  if (byControls && isVisible(byControls)) return byControls;
  return [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .find((button) => /toggle calendar|open calendar|calendar/i.test(`${button.getAttribute("aria-label") || ""} ${button.getAttribute("title") || ""} ${nearbyText(button)}`));
}

function calendarDateDescription(schedule) {
  const monthName = new Date(schedule.year, schedule.month - 1, schedule.day).toLocaleDateString("en-US", { month: "long" });
  return {
    iso: schedule.isoDate,
    us: `${schedule.month}/${schedule.day}/${schedule.year}`,
    long: `${monthName} ${schedule.day}, ${schedule.year}`,
    monthName,
  };
}

function findScheduleCalendarDay(schedule) {
  const target = calendarDateDescription(schedule);
  const buttons = [...document.querySelectorAll("button, [role='button'], [role='gridcell']")]
    .filter(isVisible)
    .filter((element) => element.getAttribute("aria-disabled") !== "true" && !element.disabled);
  const fullDateMatch = buttons.find((element) => {
    const details = [
      element.getAttribute("aria-label"),
      element.getAttribute("data-date"),
      element.getAttribute("data-day"),
      element.getAttribute("title"),
      element.value,
    ]
      .filter(Boolean)
      .join(" ");
    const comparable = normalizeComparableValue(details);
    const dayMonthYear = normalizeText(`${schedule.day} ${target.monthName} ${schedule.year}`);
    return (
      comparable.includes(target.iso) ||
      comparable.includes(target.us) ||
      comparable.includes(target.long.toLowerCase()) ||
      normalizeText(details).includes(dayMonthYear)
    );
  });
  if (fullDateMatch) return fullDateMatch;

  const visibleCalendarText = visibleCalendarContainers()
    .map((element) => element.innerText || element.textContent || "")
    .filter(Boolean)
    .join(" ");
  const calendarMonthVisible = new RegExp(`${target.monthName}\\s+${schedule.year}`, "i").test(visibleCalendarText);
  if (!calendarMonthVisible) return null;
  return buttons.find((element) => (element.innerText || element.textContent || "").trim() === String(schedule.day)) || null;
}

function visibleCalendarContainers() {
  const containers = [...document.querySelectorAll('[role="dialog"], [role="grid"], [role="application"], .calendar, [class*="calendar" i], [data-testid*="calendar" i], div')]
    .filter(isVisible)
    .filter((element) => /january|february|march|april|may|june|july|august|september|october|november|december/i.test(element.innerText || element.textContent || ""));
  return containers.length ? containers : [document.body].filter(Boolean);
}

function findScheduleCalendarNextMonth() {
  return [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .find((element) => {
      const text = `${element.getAttribute("aria-label") || ""} ${element.getAttribute("title") || ""} ${element.innerText || element.textContent || ""}`;
      return /next (?:month|calendar)|calendar next|next month/i.test(text) || /\bnext-month\b/i.test(String(element.className || ""));
    });
}

function findScheduleDayField() {
  return [...document.querySelectorAll("input, textarea, [role='textbox']")]
    .filter(isVisible)
    .find((element) => {
      const text = normalizeText(
        [element.id, element.name, element.getAttribute("aria-label"), labelText(element), nearbyText(element)].filter(Boolean).join(" ")
      );
      return /schedulestartdate|day|listingstartdate|startdate/.test(text);
    });
}

function findScheduleDateElement() {
  const scheduleDayField = findScheduleDayField();
  if (scheduleDayField) return scheduleDayField;
  const fields = candidateFields().filter(
    (field) => /schedule|listingstart|startdate|starttime|date|time|goeslive/.test(field.haystack) || ["date", "time"].includes(field.element.type)
  );
  return (
    fields.find((field) => /date|day|start/.test(field.haystack) && !/time|hour|minute|am|pm/.test(field.haystack))?.element ||
    fields.find((field) => field.element.type === "date")?.element ||
    null
  );
}

function scheduleDateFieldMatches(element, schedule) {
  if (!element) return false;
  const value = String(element.value || element.textContent || "");
  const match = value.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (!match) return value === schedule.isoDate;
  const [, month, day, year] = match;
  return `${Number(month)}/${Number(day)}/${year}` === `${Number(schedule.month)}/${Number(schedule.day)}/${schedule.year}`;
}

async function setScheduleTimeButtons(schedule) {
  const timeButtons = scheduleTimeButtons();
  const hourOk = await setVisibleDropdownButtonValue(/hours/i, String(schedule.hour12), [String(schedule.hour12).padStart(2, "0")], timeButtons.hour);
  const minuteOk = await setVisibleDropdownButtonValue(/minutes/i, schedule.minute, [], timeButtons.minute);
  const meridiemOk = await setScheduleMeridiem(schedule.suffix);
  return Boolean(hourOk && minuteOk && meridiemOk && scheduleTimeMatches(schedule));
}

function scheduleTimeButtons() {
  const groups = [...document.querySelectorAll("[role='group'], fieldset, div")]
    .filter(isVisible)
    .filter((element) => {
      const text = normalizeText(element.innerText || element.textContent || "");
      return text.includes("time") && text.includes("hours") && text.includes("minutes");
    })
    .sort((a, b) => (a.innerText || "").length - (b.innerText || "").length);
  const group = groups[0];
  const buttons = (group ? [...group.querySelectorAll("button, [role='button']")] : [...document.querySelectorAll("button, [role='button']")])
    .filter(isVisible)
    .filter((button) => /^(?:\d{1,2}|AM|PM)$/i.test((button.innerText || button.textContent || "").trim()));
  const numeric = buttons.filter((button) => /^\d{1,2}$/.test((button.innerText || button.textContent || "").trim()));
  return {
    hour: numeric[0] || null,
    minute: numeric[1] || null,
    meridiem: buttons.find((button) => /^(AM|PM)$/i.test((button.innerText || button.textContent || "").trim())) || null,
  };
}

async function setVisibleDropdownButtonValue(buttonPattern, value, aliases = [], preferredButton = null) {
  const expectedValues = [value, ...aliases].map(String).filter(Boolean);
  const expectedComparable = expectedValues.map(normalizeComparableValue);
  const expectedNumbers = expectedValues.map((item) => Number(item)).filter((item) => Number.isFinite(item));
  const optionMatches = (text) => {
    const comparable = normalizeComparableValue(text);
    if (expectedComparable.some((expected) => comparable === expected)) return true;
    const numeric = Number(comparable);
    return Number.isFinite(numeric) && expectedNumbers.includes(numeric);
  };
  const button =
    (preferredButton && isVisible(preferredButton) ? preferredButton : null) ||
    [...document.querySelectorAll("button, [role='button']")]
      .filter(isVisible)
      .find((element) => buttonPattern.test(`${element.getAttribute("aria-label") || ""} ${element.innerText || element.textContent || ""}`));
  if (!button || typeof button.click !== "function") return false;
  const current = normalizeComparableValue(button.innerText || button.textContent || "");
  if (optionMatches(current)) return true;
  button.click();
  await delay(350);
  const option = [...document.querySelectorAll("[role='option'], button, [role='menuitem'], li")]
    .filter(isVisible)
    .find((element) => optionMatches(element.innerText || element.textContent || ""));
  if (!option || typeof option.click !== "function") return false;
  option.click();
  await delay(350);
  return optionMatches(button.innerText || button.textContent || "");
}

async function setVisibleButtonValue(buttonPattern) {
  const button = [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .find((element) => buttonPattern.test((element.innerText || element.textContent || "").trim()));
  if (!button || typeof button.click !== "function") return false;
  button.click();
  await delay(250);
  return true;
}

async function setScheduleMeridiem(suffix) {
  const expected = String(suffix || "").toUpperCase();
  if (!expected) return false;
  if (await setScheduleMeridiemSelect(expected) && scheduleMeridiemReadsAs(expected)) return true;

  let opener = currentScheduleMeridiemButton();
  if (opener && elementText(opener).toUpperCase() === expected) return true;
  if (opener) {
    opener.click();
    await waitForCondition(() => Boolean(findScheduleMeridiemOption(expected, opener)), 2500, 100);
  }
  const target = findScheduleMeridiemOption(expected, opener);
  if (!target || typeof target.click !== "function") return false;
  target.click();
  await waitForCondition(() => scheduleMeridiemReadsAs(expected), 2500, 100);
  if (scheduleMeridiemReadsAs(expected)) return true;

  opener = currentScheduleMeridiemButton();
  if (!opener) return false;
  opener.click();
  await delay(150);
  const refreshedTarget = findScheduleMeridiemOption(expected, opener);
  if (!refreshedTarget) return false;
  refreshedTarget.click();
  refreshedTarget.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
  refreshedTarget.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  refreshedTarget.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await waitForCondition(() => scheduleMeridiemReadsAs(expected), 2500, 100);
  return scheduleMeridiemReadsAs(expected);
}

async function setScheduleMeridiemSelect(expected) {
  const select = [...document.querySelectorAll("select")]
    .filter(isVisible)
    .find((element) => [...element.options || []].some((option) => /^(AM|PM)$/i.test((option.textContent || option.value || "").trim())));
  if (!select) return false;
  const option = [...select.options].find((item) => (item.textContent || item.value || "").trim().toUpperCase() === expected);
  if (!option) return false;
  const nativeSetter = typeof HTMLSelectElement !== "undefined"
    ? Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set
    : null;
  if (nativeSetter) nativeSetter.call(select, option.value);
  else select.value = option.value;
  select.dispatchEvent(new Event("input", { bubbles: true }));
  select.dispatchEvent(new Event("change", { bubbles: true }));
  await delay(300);
  return (select.options[select.selectedIndex]?.textContent || select.value || "").trim().toUpperCase() === expected;
}

function findScheduleMeridiemOption(expected, opener = null) {
  return [...document.querySelectorAll("[role='option'], [role='menuitem'], li, button")]
    .filter(isVisible)
    .filter((element) => element !== opener)
    .find((element) => (element.innerText || element.textContent || "").trim().toUpperCase() === expected) || null;
}

function scheduleTimeMatches(schedule) {
  const hour = normalizeComparableValue(String(schedule.hour12));
  const hourPadded = normalizeComparableValue(String(schedule.hour12).padStart(2, "0"));
  const minute = normalizeComparableValue(schedule.minute);
  const hasButtonTime = [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .map((button) => normalizeComparableValue(button.innerText || button.textContent || ""))
    .filter(Boolean);
  return (
    hasButtonTime.some((item) => item === hour || item === hourPadded) &&
    hasButtonTime.includes(minute) &&
    scheduleMeridiemReadsAs(schedule.suffix)
  );
}

function currentScheduleMeridiemButton() {
  const timeButtons = scheduleTimeButtons();
  if (timeButtons.meridiem && isVisible(timeButtons.meridiem)) return timeButtons.meridiem;
  return [...document.querySelectorAll("button, [role='button']")]
    .filter(isVisible)
    .find((element) => /^(AM|PM)$/i.test(elementText(element))) || null;
}

function scheduleMeridiemReadsAs(expected) {
  const value = String(expected || "").toUpperCase();
  if (!value) return false;
  const selectMatch = [...document.querySelectorAll("select")]
    .filter(isVisible)
    .some((select) => (select.options[select.selectedIndex]?.textContent || select.value || "").trim().toUpperCase() === value);
  if (selectMatch) return true;
  const opener = currentScheduleMeridiemButton();
  return Boolean(opener && elementText(opener).toUpperCase() === value);
}

function elementText(element) {
  return String(element?.innerText || element?.textContent || "").trim();
}

function isSelectedChoice(element) {
  const ariaSelected = String(element.getAttribute?.("aria-selected") || "").toLowerCase();
  const ariaPressed = String(element.getAttribute?.("aria-pressed") || "").toLowerCase();
  const checked = String(element.getAttribute?.("aria-checked") || "").toLowerCase();
  const className = String(element.className || "").toLowerCase();
  return ariaSelected === "true" || ariaPressed === "true" || checked === "true" || /\b(selected|active|checked)\b/.test(className);
}

function parseListingSchedule(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const pad = (number) => String(number).padStart(2, "0");
  let hour = date.getHours();
  const minute = date.getMinutes();
  const suffix = hour >= 12 ? "PM" : "AM";
  const hour12 = hour % 12 || 12;
  return {
    year: date.getFullYear(),
    month: date.getMonth() + 1,
    day: date.getDate(),
    hour12,
    minute: pad(minute),
    suffix,
    isoDate: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    usDate: `${pad(date.getMonth() + 1)}/${pad(date.getDate())}/${date.getFullYear()}`,
    time24: `${pad(hour)}:${pad(minute)}`,
    time12: `${hour12}:${pad(minute)} ${suffix}`,
  };
}

function scheduleVisible(value) {
  const normalized = normalizeComparableValue(value);
  return normalizeComparableValue(document.body?.innerText || "").includes(normalized);
}

async function applyShippingDefaults(pkg) {
  const hasShippingPrefs =
    pkg.buyer_shipping_cost !== undefined || pkg.shipping_cost_type !== undefined || Boolean(String(pkg.domestic_shipping_service || "").trim());
  if (!hasShippingPrefs) return true;

  await revealShippingOptions();
  const buyerCost = Number(pkg.buyer_shipping_cost ?? 0);
  let buyerCostOk = false;
  if (buyerCost === 0) {
    const freeShippingOk = setCheckboxByHints(["offer free shipping", "free shipping"], true);
    const visibleCostOk = setShippingCostField(0) || shippingCostReadsAsZero();
    buyerCostOk = freeShippingOk || visibleCostOk;
  } else {
    buyerCostOk = setShippingCostField(buyerCost);
  }

  const costType = String(pkg.shipping_cost_type || "").trim().toLowerCase();
  const costTypeOk = costType === "flat" ? await chooseShippingCostType("flat") : true;

  const service = String(pkg.domestic_shipping_service || "").trim();
  if (service) await chooseVisibleShippingOption(service);
  await collapseShippingMethodControls();
  return Boolean(buyerCostOk && costTypeOk);
}

async function collapseShippingMethodControls() {
  const expandedControls = [...document.querySelectorAll("button[aria-expanded='true'], [role='button'][aria-expanded='true'], [role='combobox'][aria-expanded='true']")]
    .filter(isVisible)
    .filter((element) => /shipping|service|method|delivery|economy|ground|usps/i.test(`${element.innerText || element.textContent || ""} ${nearbyText(element)}`));
  for (const control of expandedControls) {
    await clickEbayElement(control);
    await delay(150);
  }
  await closeFloatingShippingHelpers();
  const active = document.activeElement;
  if (active) {
    active.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    active.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", bubbles: true }));
    active.blur?.();
  }
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  document.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", bubbles: true }));
}

async function closeFloatingShippingHelpers() {
  const helpers = [...document.querySelectorAll("button, [role='button'], a")]
    .filter(isVisible)
    .filter((element) => {
      const text = normalizeText(`${element.getAttribute("aria-label") || ""} ${element.getAttribute("title") || ""} ${element.innerText || element.textContent || ""}`);
      const nearby = normalizeText(nearbyText(element));
      return (
        /^(close|dismiss|cancel|done)$/.test(text) &&
        /shipping|delivery|servicemethod|shipmethod|seeoptions|recommended/.test(nearby)
      );
    });
  for (const helper of helpers.slice(0, 4)) {
    await clickEbayElement(helper);
    await delay(150);
  }
}

async function finishListingEditorView() {
  await collapseShippingMethodControls();
  await delay(250);
  const target = [...document.querySelectorAll("button, a")]
    .filter(isVisible)
    .find((element) => /list for free|list it|preview listing|save for later/i.test(element.innerText || element.textContent || ""));
  if (target?.scrollIntoView) {
    target.scrollIntoView({ block: "center", inline: "nearest" });
  } else {
    scrollPageToBottom();
    await delay(500);
    scrollPageToBottom();
  }
}

function scrollPageToBottom() {
  const bottom = Math.max(
    document.body?.scrollHeight || 0,
    document.documentElement?.scrollHeight || 0,
    document.scrollingElement?.scrollHeight || 0
  );
  window.scrollTo?.(0, bottom);
  document.documentElement.scrollTop = bottom;
  if (document.body) document.body.scrollTop = bottom;
  const scrollables = [...document.querySelectorAll("main, [role='main'], div, section")]
    .filter((element) => element.scrollHeight > element.clientHeight + 80)
    .sort((a, b) => b.scrollHeight - a.scrollHeight);
  scrollables.slice(0, 3).forEach((element) => {
    element.scrollTop = element.scrollHeight;
  });
}

async function revealShippingOptions() {
  const trigger = [...document.querySelectorAll("button, [role='button'], a")]
    .filter(isVisible)
    .find((element) => {
      const text = `${element.innerText || element.textContent || ""} ${nearbyText(element)}`;
      return /show shipping options|edit shipping|change shipping/i.test(text) && !/see shipping options/i.test(text);
    });
  if (trigger && typeof trigger.click === "function") {
    trigger.click();
    await delay(500);
    return true;
  }
  return false;
}

async function chooseShippingCostType(costType) {
  const normalized = normalizeText(costType);
  if (flatShippingVisible()) return true;

  const controls = [...document.querySelectorAll("button, [role='button'], [role='combobox'], select")]
    .filter(isVisible)
    .filter((element) => /cost type|calculated|flat|same cost|buyer location/i.test(`${element.innerText || element.textContent || ""} ${nearbyText(element)}`));
  const trigger =
    controls.find((element) => /calculated:\s*cost varies by buyer location/i.test(element.innerText || element.textContent || "")) ||
    controls.find((element) => /cost type/i.test(nearbyText(element)) && /calculated|same cost|buyer location/i.test(element.innerText || element.textContent || ""));
  if (!trigger || typeof trigger.click !== "function") return false;
  trigger.click();
  await delay(500);

  const optionText = costType === "flat" ? "flat same cost to all buyers" : costType;
  const optionNormalized = normalizeText(optionText);
  const option = [...document.querySelectorAll("[role='option'], button, [role='menuitem'], li")]
    .filter(isVisible)
    .find((element) => normalizeText(element.innerText || element.textContent || "").includes(optionNormalized));
  if (!option || typeof option.click !== "function") return false;
  option.click();
  await delay(700);
  return flatShippingVisible();
}

function flatShippingVisible() {
  const text = visibleShippingText();
  return text.includes("flatsamecosttoallbuyers");
}

function setShippingCostField(cost) {
  const value = Number(cost).toFixed(2);
  const fields = candidateFields();
  const match = fields.find((field) => /domesticshippingprice|shippingcost|buyerpay|shippingprice/.test(field.haystack));
  return match ? setFieldValue(match.element, value) : false;
}

function shippingCostReadsAsZero() {
  return [...document.querySelectorAll("input, textarea")]
    .filter(isVisible)
    .some((element) => /^(0|0\.00|\$0\.00)$/.test(String(element.value || element.getAttribute("value") || "").trim()));
}

function visibleShippingText() {
  return normalizeText(document.body?.innerText || "");
}

async function chooseVisibleShippingOption(service) {
  const normalized = normalizeText(service);
  const controls = [...document.querySelectorAll("button, [role='button'], [role='combobox'], select")]
    .filter(isVisible)
    .filter((element) => /shipping|service|primary service|economy|usps|ground|standard/i.test(nearbyText(element) || element.innerText || element.textContent || ""));
  const current = controls.find((element) => normalizeText(element.innerText || element.textContent || "").includes(normalized));
  if (current) return true;
  const trigger = controls.find((element) => /primary service|shipping service|usps|ground|standard/i.test(nearbyText(element) || element.innerText || element.textContent || ""));
  if (!trigger || typeof trigger.click !== "function") return false;
  trigger.click();
  await delay(500);
  const option = [...document.querySelectorAll("button, [role='option'], [role='menuitem'], li, div")]
    .filter(isVisible)
    .find((element) => normalizeText(element.innerText || element.textContent || "").includes(normalized));
  if (!option || typeof option.click !== "function") return false;
  option.click();
  await delay(500);
  return visibleShippingText().includes(normalized);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function requestNativeEbayInput(payload) {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return false;
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage({ type: "autozs-native-ebay-input", ...payload }, (response) => {
        if (chrome.runtime?.lastError) return resolve(false);
        resolve(Boolean(response?.ok));
      });
    } catch {
      resolve(false);
    }
  });
}

async function clickEbayElement(element) {
  if (!element) return false;
  try {
    element.scrollIntoView?.({ block: "center", inline: "center" });
    await delay(150);
    const rect = element.getBoundingClientRect();
    const targetX = rect.left + rect.width / 2;
    const targetY = rect.top + rect.height / 2;
    const inViewport = targetX >= 0 && targetY >= 0 && targetX <= window.innerWidth && targetY <= window.innerHeight;
    if (rect.width > 0 && rect.height > 0 && inViewport) {
      const nativeClick = await requestNativeEbayInput({ action: "click", x: targetX, y: targetY });
      if (nativeClick) return true;
    }
  } catch {}
  if (typeof element.click !== "function") return false;
  element.click();
  return true;
}

function setCheckboxByHints(hints, checked) {
  const normalizedHints = hints.map(normalizeText);
  const controls = [...document.querySelectorAll('input[type="checkbox"], input[type="radio"]')].map((element) => ({
    element,
    haystack: normalizeText(
      [
        element.id,
        element.name,
        element.getAttribute("aria-label"),
        labelText(element),
        nearbyText(element),
      ]
        .filter(Boolean)
        .join(" ")
    ),
  }));
  const match = controls.find((control) => normalizedHints.some((hint) => control.haystack.includes(hint)));
  if (!match) return false;
  if (match.element.checked === checked) return true;
  match.element.click();
  match.element.dispatchEvent(new Event("input", { bubbles: true }));
  match.element.dispatchEvent(new Event("change", { bubbles: true }));
  return match.element.checked === checked;
}

function setFieldValue(element, value) {
  const text = String(value ?? "");
  element.focus();
  if (isRichTextElement(element)) {
    element.textContent = text;
    element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dispatchEvent(new Event("blur", { bubbles: true }));
    return fieldContainsValue(element, text);
  }
  const prototype = element.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  if (descriptor?.set) descriptor.set.call(element, text);
  else element.value = text;
  if (typeof element.setAttribute === "function") element.setAttribute("value", text);
  if (typeof element.setSelectionRange === "function") {
    try {
      element.setSelectionRange(text.length, text.length);
    } catch {}
  }
  element.dispatchEvent(new Event("focus", { bubbles: true }));
  element.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "insertText", data: text }));
  element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true }));
  return fieldContainsValue(element, text);
}

async function setEbayTextFieldValue(element, value) {
  const text = String(value ?? "");
  const valueMatches = () => shouldRequireExactTextMatch(element) ? fieldValueMatchesExactly(element, text) : fieldContainsValue(element, text);
  try {
    const nativeInput = await withEbayAssistantHidden(async () => {
      const focused = await focusTextFieldForNativeReplacement(element);
      if (!focused) return false;
      return requestNativeEbayInput({ action: "replace-text", text });
    });
    if (nativeInput) {
      await delay(300);
      if (valueMatches()) return true;
    }
  } catch {}

  setFieldValue(element, text);
  await delay(250);
  if (valueMatches()) return true;

  // eBay's controlled inputs can discard a synthetic value assignment. Native
  // editing keeps the page's own input state in sync before the next action.
  try {
    element.focus();
    if (typeof element.setSelectionRange === "function") element.setSelectionRange(0, String(element.value || "").length);
    const inserted = document.execCommand("insertText", false, text);
    if (!inserted) return false;
    await delay(300);
  } catch {
    return false;
  }
  return valueMatches();
}

async function withEbayAssistantHidden(callback) {
  const assistant = document.getElementById?.("autozs-ebay-fill-assistant");
  const previousVisibility = assistant?.style?.visibility || "";
  try {
    if (assistant?.style) assistant.style.visibility = "hidden";
    return await callback();
  } finally {
    if (assistant?.style) assistant.style.visibility = previousVisibility;
  }
}

async function focusTextFieldForNativeReplacement(element) {
  if (!element || !isVisible(element)) return false;
  try {
    element.scrollIntoView?.({ block: "center", inline: "center" });
    await delay(100);
    element.click?.();
    element.focus?.();
    selectTextFieldContents(element);
    await delay(75);
    if (elementOwnsActiveFocus(element)) return true;
    await clickEbayElement(element);
    await delay(150);
    element.focus?.();
    selectTextFieldContents(element);
    await delay(75);
    return elementOwnsActiveFocus(element);
  } catch {
    return false;
  }
}

function selectTextFieldContents(element) {
  if (!element) return;
  try {
    if (typeof element.select === "function") {
      element.select();
      return;
    }
    if (typeof element.setSelectionRange === "function") {
      element.setSelectionRange(0, String(element.value || "").length);
    }
  } catch {}
}

function elementOwnsActiveFocus(element) {
  const active = document.activeElement;
  if (!active) return true;
  if (active === element) return true;
  if (typeof element.contains === "function" && element.contains(active)) return true;
  if (isRichTextElement(element) && typeof active.closest === "function" && active.closest("[contenteditable], [role='textbox']") === element) return true;
  return false;
}

function setRichTextValue(element, value) {
  const html = String(value || "");
  const text = listingDescriptionPlainText(html);
  element.focus();
  let inserted = false;
  if (isRichTextElement(element)) {
    try {
      const selection = window.getSelection?.();
      const range = document.createRange?.();
      if (selection && range) {
        range.selectNodeContents(element);
        selection.removeAllRanges();
        selection.addRange(range);
      }
      inserted = Boolean(document.execCommand?.(looksLikeHtml(html) ? "insertHTML" : "insertText", false, looksLikeHtml(html) ? html : text));
    } catch {}
  }
  if (!inserted) {
    if (looksLikeHtml(html)) {
      element.innerHTML = html;
    } else {
      element.textContent = text;
    }
  }
  element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertHTML", data: html }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true }));
  return fieldContainsValue(element, text);
}

function isRichTextElement(element) {
  const contenteditable = element?.getAttribute?.("contenteditable");
  return Boolean(
    element?.isContentEditable ||
    (contenteditable !== null && contenteditable !== undefined && String(contenteditable).toLowerCase() !== "false")
  );
}

function fieldContainsValue(element, value) {
  const expected = normalizeComparableValue(value);
  const current = normalizeComparableValue(element.value || element.textContent || "");
  return Boolean(expected) && (current.includes(expected) || expected.includes(current));
}

function shouldRequireExactTextMatch(element) {
  const tagName = String(element?.tagName || "").toUpperCase();
  if (tagName !== "INPUT") return false;
  const type = String(element.getAttribute?.("type") || "text").toLowerCase();
  return !["checkbox", "radio", "hidden", "file", "button", "submit"].includes(type);
}

function fieldValueMatchesExactly(element, value) {
  const expected = normalizeComparableValue(value);
  const current = normalizeComparableValue(element.value || element.textContent || "");
  if (!expected || !current) return false;
  if (current === expected) return true;
  const expectedNumber = normalizedNumberValue(expected);
  const currentNumber = normalizedNumberValue(current);
  return Boolean(expectedNumber && currentNumber && expectedNumber === currentNumber);
}

function normalizedNumberValue(value) {
  const cleaned = String(value || "").replace(/[^0-9.]/g, "");
  if (!cleaned || cleaned === ".") return "";
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed.toFixed(2) : "";
}

function labelText(element) {
  const labels = [];
  if (element.id) {
    const label = document.querySelector(`label[for="${cssEscape(element.id)}"]`);
    if (label) labels.push(label.innerText || label.textContent);
  }
  const wrapping = element.closest("label");
  if (wrapping) labels.push(wrapping.innerText || wrapping.textContent);
  return labels.join(" ");
}

function nearbyText(element) {
  const parent = (typeof element.closest === "function" ? element.closest("section, fieldset, div, li") : null) || element.parentElement;
  return (parent?.innerText || "").slice(0, 350);
}

function isVisible(element) {
  const style = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
}

function normalizeText(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function normalizeComparableValue(value) {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function cssEscape(value) {
  if (window.CSS && CSS.escape) return CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

function listingChecklist(pkg) {
  const uploadableImages = pkg.manual_image_paths || pkg.local_image_paths || [];
  const imageLines = uploadableImages.length
    ? uploadableImages.map((path) => `- ${path}`).join("\n")
    : (pkg.image_urls || []).map((url) => `- ${url}`).join("\n") || "- No images in package";
  return [
    "Manual review checklist:",
    `- Title: ${pkg.title || "missing"}`,
    `- Price: ${pkg.price ?? "missing"}`,
    `- SKU: ${pkg.sku || "missing"}`,
    `- Offers: ${pkg.offers_enabled === false ? "disabled" : "enabled/review"}`,
    `- Schedule: ${pkg.listing_schedule_at || "start immediately"}`,
    `- Shipping: ${pkg.shipping_cost_type || "flat"} ${pkg.domestic_shipping_service || "Economy Shipping"} / buyer pays $${Number(pkg.buyer_shipping_cost || 0).toFixed(2)}`,
    `- Images to upload/check:`,
    imageLines,
    "- Review category, shipping, returns, policies, and item specifics.",
    "- Do not click final List/Publish until you personally approve the listing.",
  ].join("\n");
}
