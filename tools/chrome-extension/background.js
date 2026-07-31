const DEBUGGER_PROTOCOL_VERSION = "1.3";
const REPORT_SYNC_CONTEXT_KEY = "autozsEbayReportSyncContext";
const REPORT_DOWNLOADS_KEY = "autozsEbayReportDownloads";
const PRODUCT_CAPTURE_ALARM = "autozs-product-capture-poll";
const PRODUCT_CAPTURE_LAST_OPENED_KEY = "autozsProductCaptureLastOpened";
const SOURCE_REFRESH_ALARM = "autozs-source-refresh-poll";
const SOURCE_REFRESH_LAST_OPENED_KEY = "autozsSourceRefreshLastOpened";
const LISTING_JOB_ALARM = "autozs-listing-job-poll";
const LISTING_JOB_LAST_OPENED_KEY = "autozsListingJobLastOpened";
const HOME_DEPOT_LAST_CLEANED_BATCH_KEY = "autozsHomeDepotLastCleanedBatch";
const HOME_DEPOT_POST_CLEANUP_ERRORS_KEY = "autozsHomeDepotPostCleanupErrors";
const HOME_DEPOT_SOURCE_WORKER_PAUSED_KEY = "autozsHomeDepotSourceWorkerPaused";
const SOURCE_REFRESH_MIN_GAP_MS = 75 * 1000;
const EBAY_REVISION_ALARM = "autozs-ebay-revision-poll";
const EBAY_REVISION_LAST_OPENED_KEY = "autozsEbayRevisionLastOpened";
const EBAY_REVISION_BATCH_ALARM = "autozs-ebay-revision-batch-poll";
const EBAY_REVISION_BATCH_LAST_OPENED_KEY = "autozsEbayRevisionBatchLastOpened";
const EBAY_REVISION_RESULT_CONTEXT_KEY = "autozsEbayRevisionResultContext";
const EBAY_REVISION_RESULT_DOWNLOADS_KEY = "autozsEbayRevisionResultDownloads";
const EBAY_TRAFFIC_ALARM = "autozs-ebay-traffic-poll";
const EBAY_TRAFFIC_LAST_OPENED_KEY = "autozsEbayTrafficLastOpened";
const EBAY_ACTIVE_LISTINGS_ALARM = "autozs-ebay-active-listings-poll";
const EBAY_ACTIVE_LISTINGS_LAST_OPENED_KEY = "autozsEbayActiveListingsLastOpened";
const EBAY_ORDER_ALARM = "autozs-ebay-order-poll";
const EBAY_ORDER_LAST_OPENED_KEY = "autozsEbayOrderLastOpened";
const SUPPLIER_ORDER_ALARM = "autozs-supplier-order-poll";
const SUPPLIER_ORDER_LAST_OPENED_KEY = "autozsSupplierOrderLastOpened";
const SUPPLIER_CHECKOUT_TOKENS_KEY = "autozsSupplierCheckoutTokens";
const CUSTOMER_MESSAGE_ALARM = "autozs-customer-message-poll";
const CUSTOMER_MESSAGE_LAST_OPENED_KEY = "autozsCustomerMessageLastOpened";
const CUSTOMER_MESSAGE_PAYLOADS_KEY = "autozsCustomerMessagePayloads";
const LOCAL_API = "https://desktop-56u49jf.tailb2892a.ts.net:8443";
const LOCAL_CHECKOUT_API = "http://127.0.0.1:8000";
const AUTOZS_WORKER_MODE_KEY = "autozsWorkerMode";
const PRODUCT_CAPTURE_MIN_GAP_MS = 15 * 1000;
const HOME_DEPOT_WORKER_TAB_MAX_AGE_MS = 15 * 60 * 1000;
const AUTOZS_WORKER_OPENED_AT_PARAM = "autozs_worker_opened_at";

const PRODUCT_CAPTURE_WORKER_ID_KEY = "autozsProductCaptureWorkerId";

async function productCaptureWorkerId() {
  const stored = await chrome.storage.local.get(PRODUCT_CAPTURE_WORKER_ID_KEY);
  const existing = String(stored?.[PRODUCT_CAPTURE_WORKER_ID_KEY] || "").trim();
  if (existing) return existing;

  const extensionName = String(chrome.runtime?.getManifest?.().name || "AutoZS");
  const profileToken =
    globalThis.crypto?.randomUUID?.() ||
    `${String(chrome.runtime?.id || "unpacked")}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const workerId = `${extensionName}:${profileToken}`;
  await chrome.storage.local.set({ [PRODUCT_CAPTURE_WORKER_ID_KEY]: workerId });
  return workerId;
}

function defaultAutozsWorkerMode() {
  if (isBackupCaptureExtension()) return "capture";
  return isWindowsPlatform() ? "operations" : "viewer";
}

function isBackupCaptureExtension() {
  return /Home Depot Backup/i.test(String(chrome.runtime?.getManifest?.().name || ""));
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

function isDashboardTab(tab) {
  try {
    const parsed = new URL(tab?.url || "");
    return parsed.hostname === "desktop-56u49jf.tailb2892a.ts.net"
      || parsed.hostname === "127.0.0.1"
      || parsed.hostname === "localhost";
  } catch {
    return false;
  }
}

async function readAutozsWorkerMode() {
  if (isBackupCaptureExtension()) return "capture";
  try {
    const stored = await chrome.storage.local.get(AUTOZS_WORKER_MODE_KEY);
    const mode = stored?.[AUTOZS_WORKER_MODE_KEY];
    return mode === "operations" || mode === "capture" || mode === "viewer" ? mode : defaultAutozsWorkerMode();
  } catch {
    return defaultAutozsWorkerMode();
  }
}

async function canRunAutozsWorkerJobs() {
  return isWindowsPlatform() && (await readAutozsWorkerMode()) === "operations";
}

function isEbayUrl(url) {
  try {
    return /(^|\.)ebay\.com$/i.test(new URL(url || "").hostname);
  } catch {
    return false;
  }
}

async function closeUnsafeBackupEbayTabs() {
  if (!isBackupCaptureExtension()) return;
  const tabs = await chrome.tabs.query({});
  const ebayTabIds = (tabs || [])
    .filter((tab) => isEbayUrl(tab.url || tab.pendingUrl))
    .map((tab) => tab.id)
    .filter(Boolean);
  if (ebayTabIds.length) await chrome.tabs.remove(ebayTabIds);
}

chrome.tabs?.onCreated?.addListener?.((tab) => {
  if (isBackupCaptureExtension() && isEbayUrl(tab?.pendingUrl || tab?.url)) {
    Promise.resolve(chrome.tabs.remove(tab.id)).catch(() => {});
  }
});

chrome.tabs?.onUpdated?.addListener?.((tabId, changeInfo, tab) => {
  if (
    isBackupCaptureExtension()
    && isEbayUrl(changeInfo?.url || tab?.pendingUrl || tab?.url)
  ) {
    Promise.resolve(chrome.tabs.remove(tabId)).catch(() => {});
  }
});

async function canRunAutozsSourceJobs() {
  if (!isWindowsPlatform()) return false;
  const mode = await readAutozsWorkerMode();
  if (mode === "capture") return true;
  if (mode !== "operations") return false;
  const stored = await chrome.storage.local.get(HOME_DEPOT_SOURCE_WORKER_PAUSED_KEY);
  return stored?.[HOME_DEPOT_SOURCE_WORKER_PAUSED_KEY] !== true;
}

async function clearHomeDepotBatchState() {
  if (!(await canRunAutozsSourceJobs())) return { cleared: 0, skipped: true };
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
  return /\.(csv|tsv|txt|zip)(?:$|\?)/i.test(item?.filename || item?.url || "") && (/ebay/i.test(source) || /all-active-listings|all-orders/i.test(source));
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

function isProductCaptureRunnerUrl(url) {
  try {
    const parsed = new URL(url || "");
    return parsed.hostname === "www.homedepot.com"
      && parsed.searchParams.get("ea_auto_import") === "1"
      && parsed.searchParams.has("autozs_capture_product_id");
  } catch {
    return false;
  }
}

function isAutomaticProductImportUrl(url) {
  try {
    const parsed = new URL(url || "");
    return parsed.hostname === "www.homedepot.com"
      && parsed.searchParams.get("ea_auto_import") === "1"
      && !parsed.searchParams.has("autozs_refresh_job");
  } catch {
    return false;
  }
}

function stampedHomeDepotWorkerUrl(url, openedAt = Date.now()) {
  const parsed = new URL(url);
  parsed.searchParams.set(AUTOZS_WORKER_OPENED_AT_PARAM, String(openedAt));
  return parsed.href;
}

async function cleanupStaleHomeDepotWorkerTabs(now = Date.now()) {
  const tabs = await chrome.tabs.query({ url: "https://www.homedepot.com/*" });
  const stale = tabs.filter((tab) => {
    try {
      const parsed = new URL(tab.url || "");
      const automated = parsed.searchParams.get("ea_auto_import") === "1"
        || parsed.searchParams.has("autozs_refresh_job");
      const openedAt = Number(
        parsed.searchParams.get(AUTOZS_WORKER_OPENED_AT_PARAM)
        || tab.lastAccessed
        || 0
      );
      return automated && openedAt > 0 && now - openedAt >= HOME_DEPOT_WORKER_TAB_MAX_AGE_MS;
    } catch {
      return false;
    }
  });
  await Promise.all(stale.map(async (tab) => {
    try {
      const parsed = new URL(tab.url || "");
      const refreshJobId = Number(parsed.searchParams.get("autozs_refresh_job") || 0);
      if (refreshJobId) {
        await localApiJson(`/source-refresh/jobs/${refreshJobId}/failed`, {
          method: "POST",
          body: JSON.stringify({
            message: "Home Depot worker tab exceeded the 15-minute limit and was closed automatically.",
          }),
        });
      }
    } catch {}
    if (tab.id) await chrome.tabs.remove(tab.id);
  }));
  return stale.length;
}

async function closeLegacyProductImportTabs() {
  const tabs = await chrome.tabs.query({ url: "https://www.homedepot.com/*" });
  const staleTabIds = tabs
    .filter((tab) => {
      try {
        const parsed = new URL(tab.url || "");
        return parsed.searchParams.get("ea_auto_import") === "1"
          && !parsed.searchParams.has("autozs_capture_product_id")
          && !parsed.searchParams.has("autozs_refresh_job")
          && !parsed.searchParams.has("autozs_supplier_order");
      } catch {
        return false;
      }
    })
    .map((tab) => tab.id)
    .filter(Boolean);
  if (staleTabIds.length) await chrome.tabs.remove(staleTabIds);
  return staleTabIds.length;
}

async function productCaptureRunnerTab() {
  const tabs = await chrome.tabs.query({ url: "https://www.homedepot.com/*" });
  return tabs.find((tab) => isProductCaptureRunnerUrl(tab.url)) || null;
}

async function openNextProductCapture() {
  if (!(await canRunAutozsSourceJobs())) return;
  if (await productCaptureRunnerTab()) return;
  if (await hasRunningSourceRefreshJob()) return;
  const stored = await chrome.storage.local.get(PRODUCT_CAPTURE_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[PRODUCT_CAPTURE_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < PRODUCT_CAPTURE_MIN_GAP_MS) return;
  const item = await localApiJson("/products/capture-queue/claim", {
    method: "POST",
    body: JSON.stringify({
    worker_id: await productCaptureWorkerId(),
      source_host: "homedepot.com",
    }),
  });
  if (!item?.source_url || !item?.product_id) return;
  try {
    if (new URL(item.source_url).hostname !== "www.homedepot.com") return;
  } catch {
    return;
  }
  const runnerUrl = new URL(item.source_url);
  runnerUrl.searchParams.set("ea_auto_import", "1");
  runnerUrl.searchParams.set("autozs_capture_product_id", String(item.product_id));
  runnerUrl.searchParams.set(AUTOZS_WORKER_OPENED_AT_PARAM, String(Date.now()));
  await chrome.storage.local.set({ [PRODUCT_CAPTURE_LAST_OPENED_KEY]: Date.now() });
  await chrome.tabs.create({ url: runnerUrl.href, active: false });
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
  const stampedUrl = stampedHomeDepotWorkerUrl(url);
  const tabs = await chrome.tabs.query({ url: "https://www.homedepot.com/*" });
  const runnerTab = tabs.find((tab) => isSourceRefreshRunnerUrl(tab.url));
  if (runnerTab?.id) {
    await chrome.tabs.update(runnerTab.id, { url: stampedUrl, active: false });
    return;
  }
  await chrome.tabs.create({ url: stampedUrl, active: false });
}

async function openNextSourceRefreshJob() {
  if (!(await canRunAutozsSourceJobs())) return;
  if (await productCaptureRunnerTab()) return;
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

async function readRunningListingJob() {
  try {
    const jobs = await localApiJson("/listing-jobs?status=running&limit=1");
    if (!Array.isArray(jobs) || !jobs.length) return null;
    return jobs[0];
  } catch {
    return undefined;
  }
}

// eBay's listing editor renders the DESCRIPTION block lazily. Lazy rendering
// driven by IntersectionObserver does not fire in a tab that Chrome never
// paints, so a background runner tab never gets a description editor at all and
// the fill fails with "eBay requires a description and AutoZS could not write
// one into the editor". Running the assistant a second time on a tab the user
// has since looked at succeeds, which is the same effect. Keep runner tabs
// foreground; the queue is single-flight, so this is one tab at a time.
const LISTING_RUNNER_TAB_ACTIVE = true;

const LISTING_JOB_RUNNER_TAB_KEY = "autozsListingJobRunnerTabs";

async function readListingJobRunnerTabId(jobId) {
  const stored = await chrome.storage.local.get(LISTING_JOB_RUNNER_TAB_KEY);
  const id = (stored?.[LISTING_JOB_RUNNER_TAB_KEY] || {})[String(jobId)];
  return id === undefined ? null : Number(id);
}

async function writeListingJobRunnerTabId(jobId, tabId) {
  const stored = await chrome.storage.local.get(LISTING_JOB_RUNNER_TAB_KEY);
  const map = { ...(stored?.[LISTING_JOB_RUNNER_TAB_KEY] || {}) };
  map[String(jobId)] = tabId;
  await chrome.storage.local.set({ [LISTING_JOB_RUNNER_TAB_KEY]: map });
}

async function reopenOrphanedListingJob(job) {
  if (!job?.id || !job?.assistant_url) return false;
  // Background tabs (active:false) are throttled by Chrome and can go several
  // seconds without a committed URL, so chrome.tabs.query by URL pattern can
  // miss a tab that is alive and loading fine — which made every reopen cycle
  // create ANOTHER duplicate tab instead of recognizing the one it just made.
  // Track the exact tab id we created for this job and trust chrome.tabs.get
  // (existence, not URL) before falling back to the looser URL-based search.
  const trackedTabId = await readListingJobRunnerTabId(job.id);
  if (trackedTabId !== null) {
    try {
      const trackedTab = await chrome.tabs.get(trackedTabId);
      if (trackedTab.discarded || trackedTab.status === "unloaded") {
        await chrome.tabs.reload(trackedTab.id);
      }
      return true;
    } catch {
      // Tab no longer exists; fall through to the URL-based search / reopen.
    }
  }
  const tabs = await chrome.tabs.query({ url: ["https://www.ebay.com/*", "https://sell.ebay.com/*"] });
  // A working runner navigates from the assistant URL to /lstng?draftId=...,
  // which drops autozs_job_id. Matching only on that param made the background
  // treat a healthy job as orphaned and open a SECOND runner, and two tabs
  // share one workflow key, so they corrupt each other. Any eBay listing or
  // prelist tab counts as a live runner.
  const runner = tabs.find(
    (tab) =>
      isListingJobRunnerUrl(tab.url, job.id) ||
      isListingJobRunnerUrl(tab.pendingUrl, job.id) ||
      isEbayListingWorkflowUrl(tab.url) ||
      isEbayListingWorkflowUrl(tab.pendingUrl)
  );
  if (runner) {
    // Session-restored runner tabs sit discarded/unloaded with a matching URL
    // but no live content script; wake them or the job stalls forever.
    if (runner.discarded || runner.status === "unloaded") {
      await chrome.tabs.reload(runner.id);
    }
    await writeListingJobRunnerTabId(job.id, runner.id);
    return true;
  }
  // The API's 30-minute watchdog keys off updated_at, which a reopened tab
  // never refreshes on its own, so a recovered job was still being flagged
  // "worker stopped reporting". Heartbeat here, but only a few times so a job
  // that genuinely cannot progress still fails instead of looping forever.
  const reopens = await readListingJobReopenCount(job.id);
  if (reopens >= 3) return false;
  const stored = await chrome.storage.local.get(LISTING_JOB_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[LISTING_JOB_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 75 * 1000) return false;
  await chrome.storage.local.set({ [LISTING_JOB_LAST_OPENED_KEY]: Date.now() });
  await writeListingJobReopenCount(job.id, reopens + 1);
  // Runner tabs must be ACTIVE. eBay renders the DESCRIPTION block lazily, and
  // lazy rendering driven by IntersectionObserver never fires in a tab that is
  // never painted -- so in a background tab the description editor simply does
  // not exist and the fill reports "could not write one into the editor". See
  // LISTING_RUNNER_TAB_ACTIVE.
  const created = await chrome.tabs.create({ url: job.assistant_url, active: LISTING_RUNNER_TAB_ACTIVE });
  await writeListingJobRunnerTabId(job.id, created.id);
  await heartbeatRunningListingJob(job.id, reopens + 1);
  return true;
}

const LISTING_JOB_REOPEN_KEY = "autozsListingJobReopens";

async function readListingJobReopenCount(jobId) {
  const stored = await chrome.storage.local.get(LISTING_JOB_REOPEN_KEY);
  return Number((stored?.[LISTING_JOB_REOPEN_KEY] || {})[String(jobId)] || 0);
}

async function writeListingJobReopenCount(jobId, count) {
  const stored = await chrome.storage.local.get(LISTING_JOB_REOPEN_KEY);
  const counts = { ...(stored?.[LISTING_JOB_REOPEN_KEY] || {}) };
  counts[String(jobId)] = count;
  await chrome.storage.local.set({ [LISTING_JOB_REOPEN_KEY]: counts });
}

async function heartbeatRunningListingJob(jobId, attempt) {
  try {
    await fetch(`${LOCAL_API}/listing-jobs/${encodeURIComponent(jobId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: "running",
        message: `Runner tab was reopened by AutoZS (recovery ${attempt}/3); job is still in progress.`,
      }),
    });
  } catch {}
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

function isEbayListingWorkflowUrl(url) {
  try {
    const parsed = new URL(url || "");
    return /(^|\.)ebay\.com$/i.test(parsed.hostname)
      && /^\/(?:lstng|sl\/list|sl\/prelist)\b/i.test(parsed.pathname);
  } catch {
    return false;
  }
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
  // The reopen counter is keyed only by job id and otherwise never clears, so a
  // job that once burned all 3 reopens (e.g. during a crash) stays unrecoverable
  // under that id forever, even after being fully requeued and freshly claimed.
  await writeListingJobReopenCount(job.id, 0);
  const created = await chrome.tabs.create({ url: job.assistant_url, active: LISTING_RUNNER_TAB_ACTIVE });
  await writeListingJobRunnerTabId(job.id, created.id);
  return true;
}

async function openNextListingJob() {
  if (!(await canRunAutozsWorkerJobs())) return;
  const running = await readRunningListingJob();
  if (running === undefined) return;
  if (running) {
    // A job reserved in the API without a live runner tab would otherwise sit
    // until the 30-minute stale watchdog kills it; reopen its runner instead.
    await reopenOrphanedListingJob(running);
    return;
  }
  const stored = await chrome.storage.local.get(LISTING_JOB_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[LISTING_JOB_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 75 * 1000) return;
  const result = await claimNextListingJob();
  if (!result?.job) return;
  await chrome.storage.local.set({ [LISTING_JOB_LAST_OPENED_KEY]: Date.now() });
  await openListingJobRunner(result);
}

function isSupplierOrderRunnerUrl(url, supplierOrderId = null) {
  try {
    const parsed = new URL(url || "");
    const orderId = parsed.searchParams.get("autozs_supplier_order");
    return parsed.hostname === "www.homedepot.com"
      && Boolean(orderId)
      && (supplierOrderId === null || orderId === String(supplierOrderId));
  } catch {
    return false;
  }
}

function supplierOrderRunnerUrl(supplierOrder) {
  const sourceUrl = supplierOrder?.items?.find((item) => item?.source_url)?.source_url || supplierOrder?.source_url;
  const parsed = new URL(sourceUrl || "");
  if (parsed.hostname !== "www.homedepot.com" || !/^\/p\//i.test(parsed.pathname)) {
    throw new Error("Automatic supplier checkout currently requires one Home Depot product URL.");
  }
  parsed.searchParams.set("autozs_supplier_order", String(supplierOrder.id));
  parsed.searchParams.set("autozs_checkout_canary", "1");
  return parsed.href;
}

async function rememberSupplierCheckoutToken(supplierOrder) {
  if (!supplierOrder?.id || !supplierOrder?.checkout_token) return;
  const stored = await chrome.storage.local.get(SUPPLIER_CHECKOUT_TOKENS_KEY);
  const tokens = { ...(stored?.[SUPPLIER_CHECKOUT_TOKENS_KEY] || {}) };
  tokens[String(supplierOrder.id)] = {
    token: supplierOrder.checkout_token,
    expiresAt: Date.now() + 10 * 60 * 1000,
  };
  await chrome.storage.local.set({ [SUPPLIER_CHECKOUT_TOKENS_KEY]: tokens });
}

async function readSupplierCheckoutToken(supplierOrderId) {
  const stored = await chrome.storage.local.get(SUPPLIER_CHECKOUT_TOKENS_KEY);
  const tokens = { ...(stored?.[SUPPLIER_CHECKOUT_TOKENS_KEY] || {}) };
  const entry = tokens[String(supplierOrderId)];
  if (!entry?.token || Number(entry.expiresAt || 0) < Date.now()) {
    delete tokens[String(supplierOrderId)];
    await chrome.storage.local.set({ [SUPPLIER_CHECKOUT_TOKENS_KEY]: tokens });
    return "";
  }
  return String(entry.token);
}

async function claimNextSupplierOrder() {
  return localApiJson("/supplier-orders/next", { method: "POST" });
}

async function openNextSupplierOrder() {
  if (!(await canRunAutozsWorkerJobs())) return;
  const tabs = await chrome.tabs.query({ url: "https://www.homedepot.com/*" });
  if (tabs.some((tab) => isSupplierOrderRunnerUrl(tab.url))) return;
  const stored = await chrome.storage.local.get(SUPPLIER_ORDER_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[SUPPLIER_ORDER_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 60 * 1000) return;
  const supplierOrder = await claimNextSupplierOrder();
  if (!supplierOrder?.id) return;
  await rememberSupplierCheckoutToken(supplierOrder);
  await chrome.storage.local.set({ [SUPPLIER_ORDER_LAST_OPENED_KEY]: Date.now() });
  await chrome.tabs.create({ url: supplierOrderRunnerUrl(supplierOrder), active: true });
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

async function claimNextEbayTrafficSync() {
  const accountKey = await matchedEbayAccountKey();
  if (!accountKey) return null;
  return localApiJson(`/ebay/sync-runs/traffic/next?account_key=${encodeURIComponent(accountKey)}`, {
    method: "POST",
  });
}

async function claimNextEbayActiveListingsSync() {
  const accountKey = await matchedEbayAccountKey();
  if (!accountKey) return null;
  return localApiJson(`/ebay/sync-runs/active-listings/next?account_key=${encodeURIComponent(accountKey)}`, {
    method: "POST",
  });
}

function isEbayActiveListingsRunnerUrl(url, runId = null) {
  try {
    const parsed = new URL(url || "");
    const params = new URLSearchParams(String(parsed.hash || "").replace(/^#/, ""));
    const id = params.get("autozs_sync_run");
    return parsed.hostname === "www.ebay.com"
      && /^\/sh\/lst\/active/i.test(parsed.pathname)
      && params.get("autozs_report_type") === "active_listings"
      && Boolean(id)
      && (runId === null || id === String(runId));
  } catch {
    return false;
  }
}

async function openNextEbayActiveListingsSync() {
  if (!(await canRunAutozsWorkerJobs())) return;
  const stored = await chrome.storage.local.get(EBAY_ACTIVE_LISTINGS_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[EBAY_ACTIVE_LISTINGS_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 60 * 1000) return;
  const run = await claimNextEbayActiveListingsSync();
  if (!run?.runner_url || run.status !== "running") return;
  const tabs = await chrome.tabs.query({ url: "https://www.ebay.com/sh/lst/active*" });
  const exact = tabs.find((tab) => isEbayActiveListingsRunnerUrl(tab.url, run.id));
  if (exact?.id) {
    await chrome.tabs.reload(exact.id);
  } else {
    const reusable = tabs.find((tab) => isEbayActiveListingsRunnerUrl(tab.url));
    if (reusable?.id) {
      await chrome.tabs.update(reusable.id, { url: run.runner_url, active: false });
      await chrome.tabs.reload(reusable.id);
    } else {
      await chrome.tabs.create({ url: run.runner_url, active: false });
    }
  }
  await chrome.storage.local.set({ [EBAY_ACTIVE_LISTINGS_LAST_OPENED_KEY]: Date.now() });
}

function isEbayTrafficRunnerUrl(url, runId = null) {
  try {
    const parsed = new URL(url || "");
    const id = new URLSearchParams(String(parsed.hash || "").replace(/^#/, "")).get("autozs_sync_run");
    return parsed.hostname === "www.ebay.com"
      && /^\/sh\/performance\/traffic/i.test(parsed.pathname)
      && Boolean(id)
      && (runId === null || id === String(runId));
  } catch {
    return false;
  }
}

async function openNextEbayTrafficSync() {
  if (!(await canRunAutozsWorkerJobs())) return;
  const stored = await chrome.storage.local.get(EBAY_TRAFFIC_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[EBAY_TRAFFIC_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 60 * 1000) return;
  const run = await claimNextEbayTrafficSync();
  if (!run?.runner_url || run.status !== "running") return;
  const tabs = await chrome.tabs.query({ url: "https://www.ebay.com/sh/performance/traffic*" });
  const exact = tabs.find((tab) => isEbayTrafficRunnerUrl(tab.url, run.id));
  if (exact?.id) {
    await chrome.tabs.reload(exact.id);
  } else {
    const reusable = tabs.find((tab) => isEbayTrafficRunnerUrl(tab.url));
    if (reusable?.id) {
      await chrome.tabs.update(reusable.id, { url: run.runner_url, active: false });
      await chrome.tabs.reload(reusable.id);
    } else {
      await chrome.tabs.create({ url: run.runner_url, active: false });
    }
  }
  await chrome.storage.local.set({ [EBAY_TRAFFIC_LAST_OPENED_KEY]: Date.now() });
}

async function claimNextEbayOrderSync() {
  const accountKey = await matchedEbayAccountKey();
  if (!accountKey) return null;
  return localApiJson(`/orders/sync/next?account_key=${encodeURIComponent(accountKey)}`, {
    method: "POST",
  });
}

function isEbayOrderRunnerUrl(url, runId = null) {
  try {
    const parsed = new URL(url || "");
    const params = new URLSearchParams(String(parsed.hash || "").replace(/^#/, ""));
    const id = params.get("autozs_sync_run");
    return parsed.hostname === "www.ebay.com"
      && /^\/sh\/reports\/downloads/i.test(parsed.pathname)
      && params.get("autozs_report_type") === "orders"
      && Boolean(id)
      && (runId === null || id === String(runId));
  } catch {
    return false;
  }
}

async function openNextEbayOrderSync() {
  if (!(await canRunAutozsWorkerJobs())) return;
  const stored = await chrome.storage.local.get(EBAY_ORDER_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[EBAY_ORDER_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 60 * 1000) return;
  const run = await claimNextEbayOrderSync();
  if (!run?.runner_url || run.status !== "running") return;
  const tabs = await chrome.tabs.query({ url: "https://www.ebay.com/sh/reports/downloads*" });
  const exact = tabs.find((tab) => isEbayOrderRunnerUrl(tab.url, run.id));
  if (exact?.id) {
    await chrome.tabs.reload(exact.id);
  } else {
    const reusable = tabs.find((tab) => isEbayOrderRunnerUrl(tab.url));
    if (reusable?.id) {
      await chrome.tabs.update(reusable.id, { url: run.runner_url, active: false });
      await chrome.tabs.reload(reusable.id);
    } else {
      await chrome.tabs.create({ url: run.runner_url, active: false });
    }
  }
  await chrome.storage.local.set({ [EBAY_ORDER_LAST_OPENED_KEY]: Date.now() });
}

async function claimNextCustomerMessage() {
  return localApiJson("/customer-service/messages/next", { method: "POST" });
}

function customerMessageIdFromUrl(url) {
  try {
    const parsed = new URL(url || "");
    const searchId = parsed.searchParams.get("autozs_customer_message");
    const hashId = new URLSearchParams(String(parsed.hash || "").replace(/^#/, "")).get("autozs_customer_message");
    return Number(searchId || hashId || 0);
  } catch {
    return 0;
  }
}

function isCustomerMessageRunnerUrl(url, messageId = null) {
  const id = customerMessageIdFromUrl(url);
  return Boolean(id) && (messageId === null || id === Number(messageId));
}

function customerMessageRunnerUrl(message, conversation) {
  const threadId = String(conversation?.ebay_thread_id || "");
  const orderId = threadId.startsWith("order:") ? threadId.slice("order:".length).trim() : "";
  const target = orderId
    ? new URL("https://www.ebay.com/sh/ord/details")
    : new URL("https://www.ebay.com/mys/messages");
  if (orderId) target.searchParams.set("srn", orderId);
  target.hash = new URLSearchParams({ autozs_customer_message: String(message.id) }).toString();
  return target.href;
}

async function rememberCustomerMessagePayload(message, conversation) {
  const stored = await chrome.storage.local.get(CUSTOMER_MESSAGE_PAYLOADS_KEY);
  const payloads = { ...(stored?.[CUSTOMER_MESSAGE_PAYLOADS_KEY] || {}) };
  payloads[String(message.id)] = {
    message,
    conversation,
    createdAt: Date.now(),
  };
  await chrome.storage.local.set({ [CUSTOMER_MESSAGE_PAYLOADS_KEY]: payloads });
}

async function readCustomerMessagePayload(messageId) {
  const stored = await chrome.storage.local.get(CUSTOMER_MESSAGE_PAYLOADS_KEY);
  const payloads = { ...(stored?.[CUSTOMER_MESSAGE_PAYLOADS_KEY] || {}) };
  const payload = payloads[String(messageId)];
  if (!payload || Date.now() - Number(payload.createdAt || 0) > 30 * 60 * 1000) {
    delete payloads[String(messageId)];
    await chrome.storage.local.set({ [CUSTOMER_MESSAGE_PAYLOADS_KEY]: payloads });
    return null;
  }
  return payload;
}

async function patchCustomerMessage(messageId, payload) {
  return localApiJson(`/customer-service/messages/${Number(messageId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

async function openNextCustomerMessage() {
  if (!(await canRunAutozsWorkerJobs())) return;
  const ebayTabs = await chrome.tabs.query({
    url: ["https://www.ebay.com/*", "https://sell.ebay.com/*", "https://mesg.ebay.com/*"],
  });
  if (ebayTabs.some((tab) => isCustomerMessageRunnerUrl(tab.url))) return;
  const stored = await chrome.storage.local.get(CUSTOMER_MESSAGE_LAST_OPENED_KEY);
  const lastOpened = Number(stored?.[CUSTOMER_MESSAGE_LAST_OPENED_KEY] || 0);
  if (Date.now() - lastOpened < 30 * 1000) return;
  const message = await claimNextCustomerMessage();
  if (!message?.id) return;
  const conversations = await localApiJson("/customer-service/conversations");
  const conversation = (conversations || []).find(
    (item) => Number(item.id) === Number(message.conversation_id)
  );
  if (!conversation) {
    await patchCustomerMessage(message.id, {
      status: "failed",
      error: "AutoZS could not find the eBay conversation for this queued reply.",
    });
    return;
  }
  await rememberCustomerMessagePayload(message, conversation);
  await chrome.storage.local.set({ [CUSTOMER_MESSAGE_LAST_OPENED_KEY]: Date.now() });
  await chrome.tabs.create({
    url: customerMessageRunnerUrl(message, conversation),
    active: true,
  });
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

async function uploadTrafficReportDownload(context, downloadItem) {
  const sourceUrl = downloadItem?.finalUrl || downloadItem?.url;
  if (!sourceUrl) throw new Error("The completed Seller Hub Traffic report has no source URL.");
  const response = await fetch(sourceUrl, { credentials: "include", cache: "no-store" });
  if (!response.ok) throw new Error(`Seller Hub Traffic report download returned ${response.status}`);
  const content = new Uint8Array(await response.arrayBuffer());
  if (!content.length) throw new Error("The downloaded Seller Hub Traffic report is empty.");
  return localApiJson("/stats/traffic/import-file", {
    method: "POST",
    body: JSON.stringify({
      account_key: String(context.accountKey || "manual"),
      run_id: Number(context.runId),
      filename: String(downloadItem.filename || context.filename || "ebay-active-listings-traffic.csv").split(/[\\/]/).pop(),
      report_base64: bytesToBase64(content),
    }),
  });
}

async function uploadOrderReportDownload(context, downloadItem) {
  const sourceUrl = downloadItem?.finalUrl || downloadItem?.url;
  if (!sourceUrl) throw new Error("The completed Seller Hub Orders report has no source URL.");
  const response = await fetch(sourceUrl, { credentials: "include", cache: "no-store" });
  if (!response.ok) throw new Error(`Seller Hub Orders report download returned ${response.status}`);
  const content = new Uint8Array(await response.arrayBuffer());
  if (!content.length) throw new Error("The downloaded Seller Hub Orders report is empty.");
  return localApiJson("/orders/import-file", {
    method: "POST",
    body: JSON.stringify({
      account_key: String(context.accountKey || "manual"),
      run_id: Number(context.runId),
      filename: String(downloadItem.filename || context.filename || "ebay-orders.csv").split(/[\\/]/).pop(),
      report_base64: bytesToBase64(content),
    }),
  });
}

function isEbayTab(tab) {
  try {
    const url = new URL(tab?.url || "");
    return url.protocol === "https:" && ["www.ebay.com", "sell.ebay.com", "mesg.ebay.com"].includes(url.hostname);
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
  if (message?.type === "autozs-configure-worker-mode" && isDashboardTab(sender.tab)) {
    (async () => {
      const mode = String(message.mode || "");
      if (!["operations", "capture", "viewer"].includes(mode)) throw new Error("Unsupported AutoZS worker mode.");
      await chrome.storage.local.set({
        [AUTOZS_WORKER_MODE_KEY]: mode,
        [HOME_DEPOT_SOURCE_WORKER_PAUSED_KEY]: false,
        [HOME_DEPOT_POST_CLEANUP_ERRORS_KEY]: 0,
      });
      sendResponse({ ok: true, mode });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "autozs-home-depot-refresh-success") {
    chrome.storage.local.set({ [HOME_DEPOT_POST_CLEANUP_ERRORS_KEY]: 0 })
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "autozs-home-depot-post-cleanup-error") {
    (async () => {
      const stored = await chrome.storage.local.get(HOME_DEPOT_POST_CLEANUP_ERRORS_KEY);
      const errors = Number(stored?.[HOME_DEPOT_POST_CLEANUP_ERRORS_KEY] || 0) + 1;
      await chrome.storage.local.set({ [HOME_DEPOT_POST_CLEANUP_ERRORS_KEY]: errors });
      if (errors < 3 || (await readAutozsWorkerMode()) !== "operations") {
        sendResponse({ ok: true, errors, rotated: false });
        return;
      }
      const response = await fetch(`${LOCAL_API}/browser-recovery/home-depot-backup`, {
        method: "POST",
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`AutoZS backup-profile launcher returned ${response.status}.`);
      await chrome.storage.local.set({ [HOME_DEPOT_SOURCE_WORKER_PAUSED_KEY]: true });
      sendResponse({ ok: true, errors, rotated: true, recovery: await response.json() });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (
    message?.type === "autozs-customer-message-payload" &&
    sender.tab?.id &&
    isEbayTab(sender.tab)
  ) {
    (async () => {
      const messageId = Number(message.messageId || customerMessageIdFromUrl(sender.tab.url));
      if (!messageId || customerMessageIdFromUrl(sender.tab.url) !== messageId) {
        throw new Error("This eBay tab is not assigned to that AutoZS customer message.");
      }
      const payload = await readCustomerMessagePayload(messageId);
      if (!payload) throw new Error("The queued AutoZS customer message expired.");
      sendResponse({ ok: true, payload });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (
    message?.type === "autozs-customer-message-status" &&
    sender.tab?.id &&
    isEbayTab(sender.tab)
  ) {
    (async () => {
      const messageId = Number(message.messageId || customerMessageIdFromUrl(sender.tab.url));
      if (!messageId) throw new Error("Missing AutoZS customer message ID.");
      const updated = await patchCustomerMessage(messageId, message.payload || {});
      sendResponse({ ok: true, message: updated });
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
    message?.type === "autozs-supplier-checkout-credential" &&
    sender.tab?.id &&
    isSupplierOrderRunnerUrl(sender.tab.url, Number(message.supplierOrderId))
  ) {
    (async () => {
      const supplierOrderId = Number(message.supplierOrderId);
      const token = await readSupplierCheckoutToken(supplierOrderId);
      if (!token) throw new Error("The local supplier checkout lease expired.");
      const response = await fetch(`${LOCAL_CHECKOUT_API}/supplier-orders/${supplierOrderId}/checkout-credential`, {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-AutoZS-Checkout-Token": token,
        },
      });
      if (!response.ok) throw new Error(`Local checkout credential broker returned ${response.status}.`);
      sendResponse({ ok: true, credential: await response.json() });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
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
  if (
    message?.type === "autozs-close-product-capture-tab" &&
    sender.tab?.id &&
    isAutomaticProductImportUrl(sender.tab.url)
  ) {
    chrome.tabs.remove(sender.tab.id, () => {
      sendResponse({ ok: true });
      setTimeout(() => openNextProductCapture().catch(() => {}), 1500);
    });
    return true;
  }
  if (message?.type === "autozs-start-product-capture") {
    openNextProductCapture()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
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
      if (context.reportType === "traffic") {
        try {
          await uploadTrafficReportDownload(context, (await chrome.downloads.search({ id: Number(delta.id) }))?.[0]);
        } catch (error) {
          await patchSyncRun(context.runId, {
            phase: "report_downloaded",
            message: `Traffic report downloaded; waiting for local import after direct upload failed: ${error?.message || String(error)}`,
            report_filename: context.filename,
          });
        }
      } else if (context.reportType === "orders") {
        try {
          await uploadOrderReportDownload(context, (await chrome.downloads.search({ id: Number(delta.id) }))?.[0]);
        } catch (error) {
          await patchSyncRun(context.runId, {
            phase: "report_downloaded",
            message: `Orders report downloaded; waiting for local import after direct upload failed: ${error?.message || String(error)}`,
            report_filename: context.filename,
          });
        }
      } else {
        await patchSyncRun(context.runId, {
          phase: "report_downloaded",
          message: "Active Listings report downloaded. AutoZS is importing it now.",
          report_filename: context.filename,
        });
      }
      delete downloads[String(delta.id)];
      await chrome.storage.local.set({ [REPORT_DOWNLOADS_KEY]: downloads, [REPORT_SYNC_CONTEXT_KEY]: null });
    })().catch(() => {});
  });
}

const BACKUP_ALLOWED_ALARMS = new Set([PRODUCT_CAPTURE_ALARM, SOURCE_REFRESH_ALARM]);
const AUTOZS_ALARM_SCHEDULE = [
  [PRODUCT_CAPTURE_ALARM, 0.1, 0.5],
  [SOURCE_REFRESH_ALARM, 1, 2],
  [LISTING_JOB_ALARM, 1, 2],
  [EBAY_REVISION_ALARM, 1, 2],
  [EBAY_REVISION_BATCH_ALARM, 1, 2],
  [EBAY_ACTIVE_LISTINGS_ALARM, 1, 2],
  [EBAY_TRAFFIC_ALARM, 1, 2],
  [EBAY_ORDER_ALARM, 1, 2],
  [SUPPLIER_ORDER_ALARM, 1, 2],
  [CUSTOMER_MESSAGE_ALARM, 0.1, 1],
];

async function configureAutozsAlarms() {
  for (const [name, delayInMinutes, periodInMinutes] of AUTOZS_ALARM_SCHEDULE) {
    if (isBackupCaptureExtension() && !BACKUP_ALLOWED_ALARMS.has(name)) {
      await chrome.alarms.clear(name);
      continue;
    }
    chrome.alarms.create(name, { delayInMinutes, periodInMinutes });
  }
}

if (chrome.alarms) {
  chrome.runtime.onInstalled.addListener(() => {
    closeUnsafeBackupEbayTabs().catch(() => {});
    closeLegacyProductImportTabs().catch(() => {});
    configureAutozsAlarms().catch(() => {});
  });
  chrome.runtime.onStartup.addListener(() => {
    closeUnsafeBackupEbayTabs().catch(() => {});
    closeLegacyProductImportTabs().catch(() => {});
    configureAutozsAlarms().catch(() => {});
  });
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (isBackupCaptureExtension() && !BACKUP_ALLOWED_ALARMS.has(alarm?.name)) {
      Promise.resolve(chrome.alarms.clear(alarm?.name)).catch(() => {});
      closeUnsafeBackupEbayTabs().catch(() => {});
      return;
    }
    if ([PRODUCT_CAPTURE_ALARM, SOURCE_REFRESH_ALARM].includes(alarm?.name)) {
      cleanupStaleHomeDepotWorkerTabs().catch(() => {});
    }
    if (alarm?.name === PRODUCT_CAPTURE_ALARM) openNextProductCapture().catch(() => {});
    if (alarm?.name === SOURCE_REFRESH_ALARM) openNextSourceRefreshJob().catch(() => {});
    if (alarm?.name === LISTING_JOB_ALARM) openNextListingJob().catch(() => {});
    if (alarm?.name === EBAY_REVISION_ALARM) openNextEbayRevisionJob().catch(() => {});
    if (alarm?.name === EBAY_REVISION_BATCH_ALARM) openNextEbayRevisionBatch().catch(() => {});
    if (alarm?.name === EBAY_ACTIVE_LISTINGS_ALARM) openNextEbayActiveListingsSync().catch(() => {});
    if (alarm?.name === EBAY_TRAFFIC_ALARM) openNextEbayTrafficSync().catch(() => {});
    if (alarm?.name === EBAY_ORDER_ALARM) openNextEbayOrderSync().catch(() => {});
    if (alarm?.name === SUPPLIER_ORDER_ALARM) openNextSupplierOrder().catch(() => {});
    if (alarm?.name === CUSTOMER_MESSAGE_ALARM) openNextCustomerMessage().catch(() => {});
  });
  configureAutozsAlarms().catch(() => {});
  closeUnsafeBackupEbayTabs().catch(() => {});
}
