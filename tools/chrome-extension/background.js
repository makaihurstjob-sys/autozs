const DEBUGGER_PROTOCOL_VERSION = "1.3";
const REPORT_SYNC_CONTEXT_KEY = "autozsEbayReportSyncContext";
const REPORT_DOWNLOADS_KEY = "autozsEbayReportDownloads";
const SOURCE_REFRESH_ALARM = "autozs-source-refresh-poll";
const SOURCE_REFRESH_LAST_OPENED_KEY = "autozsSourceRefreshLastOpened";
const LISTING_JOB_ALARM = "autozs-listing-job-poll";
const LISTING_JOB_LAST_OPENED_KEY = "autozsListingJobLastOpened";
const HOME_DEPOT_LAST_CLEANED_BATCH_KEY = "autozsHomeDepotLastCleanedBatch";
const SOURCE_REFRESH_MIN_GAP_MS = 75 * 1000;
const EBAY_REVISION_ALARM = "autozs-ebay-revision-poll";
const EBAY_REVISION_LAST_OPENED_KEY = "autozsEbayRevisionLastOpened";
const EBAY_REVISION_BATCH_ALARM = "autozs-ebay-revision-batch-poll";
const EBAY_REVISION_BATCH_LAST_OPENED_KEY = "autozsEbayRevisionBatchLastOpened";
const EBAY_REVISION_RESULT_CONTEXT_KEY = "autozsEbayRevisionResultContext";
const EBAY_REVISION_RESULT_DOWNLOADS_KEY = "autozsEbayRevisionResultDownloads";
const LOCAL_API = "https://desktop-56u49jf.tailb2892a.ts.net:8443";
const AUTOZS_WORKER_MODE_KEY = "autozsWorkerMode";

function defaultAutozsWorkerMode() {
  return isWindowsPlatform() ? "operations" : "viewer";
}

function workerPlatform() {
  return String(
    globalThis.navigator?.userAgentData?.platform ||
    globalThis.navigator?.platform ||
    globalThis.navigator?.userAgent ||
    ""
  );
}

function isWindowsPlatform() {
  return /\bWin|Windows\b/i.test(workerPlatform());
}

async function readAutozsWorkerMode() {
  try {
    const stored = await chrome.storage.local.get(AUTOZS_WORKER_MODE_KEY);
    const mode = stored?.[AUTOZS_WORKER_MODE_KEY];
    return mode === "operations" || mode === "viewer" ? mode : defaultAutozsWorkerMode();
  } catch {
    return defaultAutozsWorkerMode();
  }
}

async function canRunAutozsWorkerJobs() {
  return isWindowsPlatform() && (await readAutozsWorkerMode()) === "operations";
}

async function clearHomeDepotBatchState() {
  if (!(await canRunAutozsWorkerJobs())) return { cleared: 0, skipped: true };
  const cookies = await chrome.cookies.getAll({ domain: ".homedepot.com" });
  const removals = await Promise.allSettled((cookies || []).map((cookie) => {
    const protocol = cookie.secure ? "https" : "http";
    const host = String(cookie.domain || "www.homedepot.com").replace(/^\./, "");
    const details = { url: `${protocol}://${host}${cookie.path || "/"}`, name: cookie.name, storeId: cookie.storeId };
    if (cookie.partitionKey) details.partitionKey = cookie.partitionKey;
    return chrome.cookies.remove(details);
  }));
  if (chrome.browsingData?.remove) {
    await chrome.browsingData.remove(
      { origins: ["https://www.homedepot.com"] },
      {
        cache: true,
        cacheStorage: true,
        cookies: true,
        indexedDB: true,
        localStorage: true,
        serviceWorkers: true,
      }
    );
  }
  return {
    cleared: removals.filter((result) => result.status === "fulfilled" && result.value).length,
    failed: removals.filter((result) => result.status === "rejected").length,
    skipped: false,
  };
}

async function ensureHomeDepotBatchState(batchKey) {
  const normalizedBatchKey = String(batchKey || "").trim();
  if (!normalizedBatchKey) return { cleared: 0, skipped: true };
  const stored = await chrome.storage.local.get(HOME_DEPOT_LAST_CLEANED_BATCH_KEY);
  if (stored?.[HOME_DEPOT_LAST_CLEANED_BATCH_KEY] === normalizedBatchKey) {
    return { cleared: 0, alreadyCleaned: true, skipped: false };
  }
  const cleanup = await clearHomeDepotBatchState();
  if (!cleanup.skipped) {
    await chrome.storage.local.set({ [HOME_DEPOT_LAST_CLEANED_BATCH_KEY]: normalizedBatchKey });
  }
  return cleanup;
}

function reportDownloadFilename(context, originalFilename) {
  const extensionMatch = String(originalFilename || "").toLowerCase().match(/\.(csv|tsv|txt|zip)$/);
  const extension = extensionMatch?.[1] || "csv";
  const accountKey = String(context?.accountKey || "manual").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "manual";
  const reportType = String(context?.reportType || "active_listings").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "active-listings";
  return `AutoZS/ebay-${reportType}-${accountKey}-run-${Number(context?.runId)}.${extension}`;
}

function isEbayReportDownload(item) {
  const source = `${item?.url || ""} ${item?.referrer || ""} ${item?.filename || ""}`;
  return /\.(csv|tsv|txt|zip)(?:$|\?)/i.test(item?.filename || item?.url || "") && (/ebay/i.test(source) || /all-active-listings/i.test(source));
}

async function patchSyncRun(runId, payload) {
  const response = await fetch(`${LOCAL_API}/ebay/sync-runs/${Number(runId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`AutoZS sync update returned ${response.status}`);
  return response.json();
}

async function localApiJson(path, options = {}) {
  const response = await fetch(`${LOCAL_API}${path}`, {
    cache: "no-store",
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) throw new Error(`AutoZS API returned ${response.status}`);
  return response.json();
}

async function hasRunningSourceRefreshJob() {
  try {
    const payload = await localApiJson("/source-refresh/jobs/running");
    return Boolean(payload?.running);
  } catch {
    return false;
  }
}

async function claimNextSourceRefreshJob() {
  return localApiJson("/source-refresh/jobs/next", { method: "POST" });
}

function isSourceRefreshRunnerUrl(url) {
  try {
    const parsed = new URL(url || "");
    return parsed.hostname === "www.homedepot.com" && parsed.searchParams.has("autozs_refresh_job");
  } catch {
    return false;
  }
}

async function openSourceRefreshRunnerUrl(url) {
  const tabs = await chrome.tabs.query({ url: "https://www.homedepot.com/*" });
  const runnerTab = tabs.find((tab) => isSourceRefreshRunnerUrl(tab.url));
  if (runnerTab?.id) {
    await chrome.tabs.update(runnerTab.id, { url, active: false });
    return;
  }
  await chrome.tabs.create({ url, active: false });
}

async function openNextSourceRefreshJob() {
  if (!(await canRunAutozsWorkerJobs())) return;
  if (await hasRunningSourceRefreshJob()) return;
  const stored = await chrome.storage.local.get(SOURCE_REFRESH_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[SOURCE_REFRESH_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < SOURCE_REFRESH_MIN_GAP_MS) return;
  const job = await claimNextSourceRefreshJob();
  if (!job?.runner_url) return;
  if (Number(job.attempts || 0) > 1) await clearHomeDepotBatchState();
  else await ensureHomeDepotBatchState(job.batch_key);
  await chrome.storage.local.set({ [SOURCE_REFRESH_LAST_OPENED_KEY]: Date.now() });
  await openSourceRefreshRunnerUrl(job.runner_url);
}

async function hasRunningListingJob() {
  try {
    const jobs = await localApiJson("/listing-jobs?status=running&limit=1");
    return Array.isArray(jobs) && jobs.length > 0;
  } catch {
    return true;
  }
}

async function claimNextListingJob() {
  const response = await fetch(`${LOCAL_API}/listing-jobs/next`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`AutoZS API returned ${response.status}`);
  return response.json();
}

function isListingJobRunnerUrl(url, jobId = null) {
  try {
    const parsed = new URL(url || "");
    const parsedJobId = parsed.searchParams.get("autozs_job_id") || new URLSearchParams(parsed.hash.replace(/^#/, "")).get("autozs_job_id");
    return (parsed.hostname === "www.ebay.com" || parsed.hostname === "sell.ebay.com")
      && Boolean(parsedJobId)
      && (jobId === null || parsedJobId === String(jobId));
  } catch {
    return false;
  }
}

async function openListingJobRunner(result) {
  const job = result?.job;
  if (!job?.assistant_url || !result?.package) return false;
  const tabs = await chrome.tabs.query({ url: ["https://www.ebay.com/*", "https://sell.ebay.com/*"] });
  const existing = tabs.find((tab) => isListingJobRunnerUrl(tab.url));
  if (existing?.id) {
    // eBay keeps parts of the listing editor in client-side state. Reusing a
    // runner tab can therefore leave the next product attached to the previous
    // draft even after changing the URL. A fresh tab gives every job a clean
    // editor and prevents stale draft ownership from leaking between products.
    await chrome.tabs.remove(existing.id);
  }
  await chrome.tabs.create({ url: job.assistant_url, active: false });
  return true;
}

async function openNextListingJob() {
  if (!(await canRunAutozsWorkerJobs())) return;
  if (await hasRunningListingJob()) return;
  const stored = await chrome.storage.local.get(LISTING_JOB_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[LISTING_JOB_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 75 * 1000) return;
  const result = await claimNextListingJob();
  if (!result?.job) return;
  await chrome.storage.local.set({ [LISTING_JOB_LAST_OPENED_KEY]: Date.now() });
  await openListingJobRunner(result);
}

async function claimNextEbayRevisionJob() {
  const response = await fetch(`${LOCAL_API}/ebay/revision-jobs/next`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`AutoZS API returned ${response.status}`);
  return response.json();
}

function isEbayRevisionRunnerUrl(url, jobId = null) {
  try {
    const parsed = new URL(url || "");
    const revisionId = parsed.searchParams.get("autozs_revision_job_id");
    return (parsed.hostname === "www.ebay.com" || parsed.hostname === "sell.ebay.com")
      && parsed.searchParams.get("autozs_workflow") === "revise_price"
      && Boolean(revisionId)
      && (jobId === null || revisionId === String(jobId));
  } catch {
    return false;
  }
}

async function openEbayRevisionRunner(job) {
  if (!job?.assistant_url || job.status !== "running") return false;
  const tabs = await chrome.tabs.query({ url: ["https://www.ebay.com/*", "https://sell.ebay.com/*"] });
  const exact = tabs.find((tab) => isEbayRevisionRunnerUrl(tab.url, job.id));
  if (exact?.id) return true;
  const reusable = tabs.find((tab) => isEbayRevisionRunnerUrl(tab.url));
  if (reusable?.id) {
    await chrome.tabs.update(reusable.id, { url: job.assistant_url, active: false });
    return true;
  }
  await chrome.tabs.create({ url: job.assistant_url, active: false });
  return true;
}

async function openNextEbayRevisionJob() {
  if (!(await canRunAutozsWorkerJobs())) return;
  const stored = await chrome.storage.local.get(EBAY_REVISION_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[EBAY_REVISION_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 30 * 1000) return;
  const job = await claimNextEbayRevisionJob();
  if (!job || job.status !== "running") return;
  const opened = await openEbayRevisionRunner(job);
  if (opened) await chrome.storage.local.set({ [EBAY_REVISION_LAST_OPENED_KEY]: Date.now() });
}

async function matchedEbayAccountKey() {
  const accounts = await localApiJson("/ebay/accounts");
  for (const account of accounts || []) {
    const key = String(account?.key || account?.account_id || "");
    if (!key) continue;
    try {
      const status = await localApiJson(`/ebay/browser-account?account_key=${encodeURIComponent(key)}`);
      if (status?.can_list) return key;
    } catch {}
  }
  return null;
}

async function claimNextEbayRevisionBatch() {
  const accountKey = await matchedEbayAccountKey();
  if (!accountKey) return null;
  const response = await fetch(
    `${LOCAL_API}/ebay/revision-batches/next?account_key=${encodeURIComponent(accountKey)}&limit=25`,
    { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" } }
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`AutoZS revision batch API returned ${response.status}`);
  return response.json();
}

function isEbayRevisionBatchRunnerUrl(url, batchId = null) {
  try {
    const parsed = new URL(url || "");
    const id = parsed.searchParams.get("autozs_revision_batch");
    return parsed.hostname === "www.ebay.com"
      && /^\/sh\/reports\/uploads/i.test(parsed.pathname)
      && Boolean(id)
      && (batchId === null || id === String(batchId));
  } catch {
    return false;
  }
}

async function openNextEbayRevisionBatch() {
  if (!(await canRunAutozsWorkerJobs())) return;
  const stored = await chrome.storage.local.get(EBAY_REVISION_BATCH_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[EBAY_REVISION_BATCH_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 60 * 1000) return;
  const batch = await claimNextEbayRevisionBatch();
  if (!batch?.runner_url || !["prepared", "uploading", "waiting_results"].includes(batch.status)) return;
  const tabs = await chrome.tabs.query({ url: "https://www.ebay.com/sh/reports/uploads*" });
  const exact = tabs.find((tab) => isEbayRevisionBatchRunnerUrl(tab.url, batch.id));
  if (!exact?.id) {
    const reusable = tabs.find((tab) => isEbayRevisionBatchRunnerUrl(tab.url));
    if (reusable?.id) await chrome.tabs.update(reusable.id, { url: batch.runner_url, active: false });
    else await chrome.tabs.create({ url: batch.runner_url, active: false });
  }
  await chrome.storage.local.set({ [EBAY_REVISION_BATCH_LAST_OPENED_KEY]: Date.now() });
}

function revisionResultFilename(context, originalFilename) {
  const extensionMatch = String(originalFilename || "").toLowerCase().match(/\.(csv|tsv|txt|zip)$/);
  const extension = extensionMatch?.[1] || "csv";
  const accountKey = String(context?.accountKey || "manual").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "manual";
  return `AutoZS/ebay-revision-results-${accountKey}-batch-${Number(context?.batchId)}.${extension}`;
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

async function uploadRevisionResultDownload(context, downloadItem) {
  const sourceUrl = downloadItem?.finalUrl || downloadItem?.url;
  if (!sourceUrl) throw new Error("The completed eBay result download has no source URL.");
  const response = await fetch(sourceUrl, { credentials: "include", cache: "no-store" });
  if (!response.ok) throw new Error(`eBay result download returned ${response.status}`);
  const content = new Uint8Array(await response.arrayBuffer());
  if (!content.length) throw new Error("The downloaded eBay result is empty.");
  return localApiJson(`/ebay/revision-batches/${Number(context.batchId)}/results`, {
    method: "POST",
    body: JSON.stringify({
      filename: String(downloadItem.filename || context.filename || "ebay-revision-result.csv").split(/[\\/]/).pop(),
      result_base64: bytesToBase64(content),
    }),
  });
}

function isEbayTab(tab) {
  try {
    const url = new URL(tab?.url || "");
    return url.protocol === "https:" && (url.hostname === "www.ebay.com" || url.hostname === "sell.ebay.com");
  } catch {
    return false;
  }
}

async function withDebugger(tabId, action) {
  const target = { tabId };
  await chrome.debugger.attach(target, DEBUGGER_PROTOCOL_VERSION);
  try {
    return await action((method, params) => chrome.debugger.sendCommand(target, method, params));
  } finally {
    try {
      await chrome.debugger.detach(target);
    } catch {}
  }
}

async function replaceFocusedText(sendCommand, text) {
  const shortcut = selectAllShortcut();
  await sendCommand("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: shortcut.key,
    code: shortcut.code,
    windowsVirtualKeyCode: shortcut.windowsVirtualKeyCode,
    nativeVirtualKeyCode: shortcut.nativeVirtualKeyCode,
  });
  await sendCommand("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "a",
    code: "KeyA",
    modifiers: shortcut.modifier,
    windowsVirtualKeyCode: 65,
    nativeVirtualKeyCode: 65,
  });
  await sendCommand("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "a",
    code: "KeyA",
    modifiers: shortcut.modifier,
    windowsVirtualKeyCode: 65,
    nativeVirtualKeyCode: 65,
  });
  await sendCommand("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: shortcut.key,
    code: shortcut.code,
    windowsVirtualKeyCode: shortcut.windowsVirtualKeyCode,
    nativeVirtualKeyCode: shortcut.nativeVirtualKeyCode,
  });
  await sendCommand("Input.insertText", { text });
}

function selectAllShortcut() {
  const platform = String(
    globalThis.navigator?.userAgentData?.platform ||
    globalThis.navigator?.platform ||
    globalThis.navigator?.userAgent ||
    ""
  );
  const isMac = /\bMac|Macintosh|darwin\b/i.test(platform);
  return isMac
    ? { key: "Meta", code: "MetaLeft", modifier: 4, windowsVirtualKeyCode: 91, nativeVirtualKeyCode: 91 }
    : { key: "Control", code: "ControlLeft", modifier: 2, windowsVirtualKeyCode: 17, nativeVirtualKeyCode: 17 };
}

async function clickAt(sendCommand, x, y) {
  const point = { x, y, button: "left", buttons: 1, clickCount: 1 };
  await sendCommand("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await sendCommand("Input.dispatchMouseEvent", { type: "mousePressed", ...point });
  await sendCommand("Input.dispatchMouseEvent", { type: "mouseReleased", ...point });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "autozs-worker-mode") {
    (async () => {
      sendResponse({
        ok: true,
        mode: await readAutozsWorkerMode(),
        canRunJobs: await canRunAutozsWorkerJobs(),
        defaultMode: defaultAutozsWorkerMode(),
        platform: workerPlatform(),
        api: LOCAL_API,
      });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "autozs-home-depot-batch-cleanup") {
    clearHomeDepotBatchState()
      .then((result) => sendResponse({ ok: true, ...result }))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "autozs-source-refresh-cooldown") {
    chrome.storage.local.set({ [SOURCE_REFRESH_LAST_OPENED_KEY]: Date.now() })
      .then(() => sendResponse({ ok: true, minimumGapMs: SOURCE_REFRESH_MIN_GAP_MS }))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (
    message?.type === "autozs-close-source-refresh-tab" &&
    sender.tab?.id &&
    isSourceRefreshRunnerUrl(sender.tab.url)
  ) {
    chrome.tabs.remove(sender.tab.id, () => sendResponse({ ok: true }));
    return true;
  }
  if (message?.type === "autozs-ebay-report-sync-context") {
    (async () => {
      const context = {
        runId: Number(message.runId),
        accountKey: String(message.accountKey || "manual"),
        reportType: String(message.reportType || "active_listings"),
        createdAt: Date.now(),
      };
      if (!context.runId) throw new Error("Missing AutoZS sync run ID.");
      await chrome.storage.local.set({ [REPORT_SYNC_CONTEXT_KEY]: context });
      sendResponse({ ok: true, context });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "autozs-close-report-runner-tab" && sender.tab?.id && isEbayTab(sender.tab)) {
    chrome.tabs.remove(sender.tab.id, () => sendResponse({ ok: true }));
    return true;
  }
  if (message?.type === "autozs-ebay-revision-result-context") {
    (async () => {
      const context = {
        batchId: Number(message.batchId),
        accountKey: String(message.accountKey || "manual"),
        createdAt: Date.now(),
      };
      if (!context.batchId) throw new Error("Missing AutoZS revision batch ID.");
      await chrome.storage.local.set({ [EBAY_REVISION_RESULT_CONTEXT_KEY]: context });
      sendResponse({ ok: true, context });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type !== "autozs-native-ebay-input" || !sender.tab?.id || !isEbayTab(sender.tab)) return undefined;

  (async () => {
    if (message.action === "replace-text") {
      const text = String(message.text || "");
      if (text.length > 100000) throw new Error("Text is too long for native eBay input.");
      await withDebugger(sender.tab.id, (sendCommand) => replaceFocusedText(sendCommand, text));
    } else if (message.action === "click") {
      const x = Number(message.x);
      const y = Number(message.y);
      if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0) throw new Error("Invalid eBay click coordinates.");
      await withDebugger(sender.tab.id, (sendCommand) => clickAt(sendCommand, x, y));
    } else {
      throw new Error("Unsupported native eBay input action.");
    }
    sendResponse({ ok: true });
  })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));

  return true;
});

if (chrome.downloads?.onDeterminingFilename && chrome.storage?.local) {
  chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
    (async () => {
      const stored = await chrome.storage.local.get([REPORT_SYNC_CONTEXT_KEY, EBAY_REVISION_RESULT_CONTEXT_KEY]);
      const revisionContext = stored?.[EBAY_REVISION_RESULT_CONTEXT_KEY];
      const freshRevision = revisionContext && Date.now() - Number(revisionContext.createdAt || 0) < 60 * 60 * 1000;
      if (freshRevision && isEbayReportDownload(item)) {
        const filename = revisionResultFilename(revisionContext, item.filename);
        const downloads = (await chrome.storage.local.get(EBAY_REVISION_RESULT_DOWNLOADS_KEY))?.[EBAY_REVISION_RESULT_DOWNLOADS_KEY] || {};
        downloads[String(item.id)] = { ...revisionContext, filename };
        await chrome.storage.local.set({ [EBAY_REVISION_RESULT_DOWNLOADS_KEY]: downloads });
        suggest({ filename, conflictAction: "overwrite" });
        return;
      }
      const context = stored?.[REPORT_SYNC_CONTEXT_KEY];
      const fresh = context && Date.now() - Number(context.createdAt || 0) < 60 * 60 * 1000;
      if (!fresh || !isEbayReportDownload(item)) {
        suggest();
        return;
      }
      const filename = reportDownloadFilename(context, item.filename);
      const downloads = (await chrome.storage.local.get(REPORT_DOWNLOADS_KEY))?.[REPORT_DOWNLOADS_KEY] || {};
      downloads[String(item.id)] = { ...context, filename };
      await chrome.storage.local.set({ [REPORT_DOWNLOADS_KEY]: downloads });
      suggest({ filename, conflictAction: "overwrite" });
    })().catch(() => suggest());
    return true;
  });

  chrome.downloads.onChanged.addListener((delta) => {
    if (delta?.state?.current !== "complete") return;
    (async () => {
      const stored = await chrome.storage.local.get([
        REPORT_DOWNLOADS_KEY,
        REPORT_SYNC_CONTEXT_KEY,
        EBAY_REVISION_RESULT_DOWNLOADS_KEY,
        EBAY_REVISION_RESULT_CONTEXT_KEY,
      ]);
      const revisionDownloads = stored?.[EBAY_REVISION_RESULT_DOWNLOADS_KEY] || {};
      const revisionContext = revisionDownloads[String(delta.id)];
      if (revisionContext) {
        try {
          const items = await chrome.downloads.search({ id: Number(delta.id) });
          const item = items?.[0];
          await uploadRevisionResultDownload(revisionContext, item);
        } catch (error) {
          await localApiJson(`/ebay/revision-batches/${revisionContext.batchId}`, {
            method: "PATCH",
            body: JSON.stringify({
              status: "needs_review",
              message: `Downloaded the eBay result, but direct import failed: ${error?.message || String(error)}`,
            }),
          });
        } finally {
          delete revisionDownloads[String(delta.id)];
          await chrome.storage.local.set({
            [EBAY_REVISION_RESULT_DOWNLOADS_KEY]: revisionDownloads,
            [EBAY_REVISION_RESULT_CONTEXT_KEY]: null,
          });
        }
        return;
      }
      const downloads = stored?.[REPORT_DOWNLOADS_KEY] || {};
      const context = downloads[String(delta.id)];
      if (!context) return;
      await patchSyncRun(context.runId, {
        phase: "report_downloaded",
        message: "Active Listings report downloaded. AutoZS is importing it now.",
        report_filename: context.filename,
      });
      delete downloads[String(delta.id)];
      await chrome.storage.local.set({ [REPORT_DOWNLOADS_KEY]: downloads, [REPORT_SYNC_CONTEXT_KEY]: null });
    })().catch(() => {});
  });
}

if (chrome.alarms) {
  chrome.runtime.onInstalled.addListener(() => {
    chrome.alarms.create(SOURCE_REFRESH_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
    chrome.alarms.create(LISTING_JOB_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
    chrome.alarms.create(EBAY_REVISION_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
    chrome.alarms.create(EBAY_REVISION_BATCH_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
  });
  chrome.runtime.onStartup.addListener(() => {
    chrome.alarms.create(SOURCE_REFRESH_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
    chrome.alarms.create(LISTING_JOB_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
    chrome.alarms.create(EBAY_REVISION_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
    chrome.alarms.create(EBAY_REVISION_BATCH_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
  });
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm?.name === SOURCE_REFRESH_ALARM) openNextSourceRefreshJob().catch(() => {});
    if (alarm?.name === LISTING_JOB_ALARM) openNextListingJob().catch(() => {});
    if (alarm?.name === EBAY_REVISION_ALARM) openNextEbayRevisionJob().catch(() => {});
    if (alarm?.name === EBAY_REVISION_BATCH_ALARM) openNextEbayRevisionBatch().catch(() => {});
  });
  chrome.alarms.create(SOURCE_REFRESH_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
  chrome.alarms.create(LISTING_JOB_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
  chrome.alarms.create(EBAY_REVISION_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
  chrome.alarms.create(EBAY_REVISION_BATCH_ALARM, { delayInMinutes: 1, periodInMinutes: 2 });
}
