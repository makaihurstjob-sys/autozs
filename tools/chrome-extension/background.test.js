const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/background.js`, "utf8");
if (!source.includes('["continue", "delivery", "delivery_continue", "edit_address", "add_new_card", "use_new_card", "add_to_cart", "checkout"].includes')) {
  throw new Error("Expected exact Add to Cart and Checkout activation to avoid reflow-prone mouse coordinates.");
}
if (!source.includes("Page.createIsolatedWorld") || !source.includes("commercehub-secure-data-capture")) {
  throw new Error("Expected approved card fields to support Home Depot's isolated Fiserv payment frames.");
}
if (!source.includes("chrome.debugger.getTargets") || !source.includes("secureTarget")) {
  throw new Error("Expected out-of-process Fiserv payment frames to use a scoped direct target debugger.");
}
if (!source.includes('use_new_card: "^add new card$"') || !source.includes('button[data-testid="use-this-card-button"]')) {
  throw new Error("Expected the approved new card to use Home Depot's exact non-purchase submit control.");
}
if (!source.includes("Secure-frame debugger attach") || !source.includes("Secure-frame debugger ${method}") || !source.includes("Secure-frame debugger detach") || !source.includes("Chrome debugger detach")) {
  throw new Error("Expected secured-frame debugger operations to time out and detach after failures.");
}

async function runNativePcInputTest() {
  let listener = null;
  const commands = [];
  const closedTabs = [];
  const createdTabs = [];
  const removedCookies = [];
  const browsingDataRemovals = [];
  let tabQueryResults = [];
  let runningListingJobs = [];
  let sourceRefreshJobs = [];
  const reloadedTabs = [];
  const storage = { autozsWorkerMode: "operations" };
  const fetched = [];
  const context = {
    console,
    URL,
    URLSearchParams,
    Uint8Array,
    btoa: (value) => Buffer.from(value, "binary").toString("base64"),
    fetch: async (url, options = {}) => {
      fetched.push({ url, options });
      if (url === "https://www.ebay.com/result.csv") {
        const bytes = Buffer.from("Action,Item number,Status\nRevise,800123456789,Success\n", "utf8");
        return {
          ok: true,
          status: 200,
          arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
        };
      }
      if (url.endsWith("/listing-jobs?status=running&limit=1")) {
        return { ok: true, status: 200, json: async () => runningListingJobs };
      }
      if (url.endsWith("/listing-jobs/next")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            job: {
              id: 92,
              status: "running",
              assistant_url: "https://www.ebay.com/sl/prelist/home?autozs_job_id=92#autozs_job_id=92",
            },
            package: { title: "Test listing" },
          }),
        };
      }
      if (url.endsWith("/products/capture-queue/claim")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            product_id: 44,
            source_url: "https://www.homedepot.com/p/Test-Capture/123456",
          }),
        };
      }
      if (url.endsWith("/source-refresh/jobs")) {
        return { ok: true, status: 200, json: async () => sourceRefreshJobs };
      }
      if (url.endsWith("/supplier-orders/next")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 14,
            status: "placing",
            checkout_token: "checkout-token-14",
            source_url: "https://www.homedepot.com/p/AutoZS-Checkout-Test/123456",
            items: [{
              source_url: "https://www.homedepot.com/p/AutoZS-Checkout-Test/123456",
              unit_price: 20,
              quantity: 1,
            }],
          }),
        };
      }
      if (url.endsWith("/customer-service/messages/next")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 5,
            conversation_id: 1,
            subject: "Important order update",
            body: "English and Spanish refund message",
            status: "sending",
          }),
        };
      }
      if (url.endsWith("/customer-service/conversations")) {
        return {
          ok: true,
          status: 200,
          json: async () => ([{
            id: 1,
            ebay_thread_id: "order:13-14947-26719",
            order_sales_record_number: "122",
            buyer_username: "buyer-user",
          }]),
        };
      }
      if (url === "https://www.ebay.com/traffic.csv") {
        const bytes = Buffer.from("Item ID,Listing title,Impressions,eBay views\n800123456789,Test listing,42,3\n", "utf8");
        return {
          ok: true,
          status: 200,
          arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: 91,
          status: "running",
          assistant_url: "https://www.ebay.com/sl/list?autozs_workflow=revise_price&autozs_revision_job_id=91",
        }),
      };
    },
    chrome: {
      browsingData: {
        remove: async (options, dataToRemove) => browsingDataRemovals.push({ options, dataToRemove }),
      },
      cookies: {
        getAll: async () => [
          { name: "_abck", domain: ".homedepot.com", path: "/", secure: true, storeId: "0" },
          { name: "bm_sz", domain: ".homedepot.com", path: "/", secure: true, storeId: "0" },
          { name: "bm_future_token", domain: ".homedepot.com", path: "/", secure: true, storeId: "0" },
          { name: "sec_cpt", domain: ".homedepot.com", path: "/", secure: true, storeId: "0" },
          { name: "THD_SESSION", domain: ".homedepot.com", path: "/", secure: true, storeId: "0" },
        ],
        remove: async (details) => {
          removedCookies.push(details);
          return details;
        },
      },
      debugger: {
        attach: async () => {},
        detach: async () => {},
        sendCommand: async (_target, method, params) => {
          commands.push({ method, params });
        },
      },
      runtime: {
        onMessage: {
          addListener: (callback) => {
            listener = callback;
          },
        },
      },
      storage: {
        local: {
          get: async (key) => ({ [key]: storage[key] }),
          set: async (values) => Object.assign(storage, values),
        },
      },
      tabs: {
        query: async () => tabQueryResults,
        create: async (options) => {
          createdTabs.push(options);
          return { id: 23, ...options };
        },
        update: async () => {},
        reload: async (tabId) => {
          reloadedTabs.push(tabId);
        },
        remove: (tabId, callback) => {
          closedTabs.push(tabId);
          callback?.();
        },
      },
    },
    navigator: { platform: "Win32" },
    setTimeout: (callback) => {
      callback();
      return 1;
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  if (!listener) throw new Error("Expected background message listener to be registered.");
  const cleanup = await context.clearHomeDepotBatchState();
  if (cleanup.cleared !== 5 || removedCookies.length !== 5) {
    throw new Error(`Expected every Home Depot cookie to be removed, got ${JSON.stringify({ cleanup, removedCookies })}`);
  }
  if (!removedCookies.some((cookie) => cookie.name === "THD_SESSION")) {
    throw new Error("Expected the Home Depot session cookie to be cleared with the blocked site state.");
  }
  if (
    browsingDataRemovals.length !== 1 ||
    !browsingDataRemovals[0].dataToRemove.cache ||
    !browsingDataRemovals[0].dataToRemove.cookies ||
    !browsingDataRemovals[0].dataToRemove.localStorage ||
    !browsingDataRemovals[0].dataToRemove.indexedDB
  ) {
    throw new Error(`Expected Home Depot cache cleanup, got ${JSON.stringify(browsingDataRemovals)}`);
  }
  const removalsBeforeBatchGuard = removedCookies.length;
  await context.ensureHomeDepotBatchState("refresh-batch-one");
  await context.ensureHomeDepotBatchState("refresh-batch-one");
  if (removedCookies.length !== removalsBeforeBatchGuard + 5) {
    throw new Error("Expected Home Depot cleanup exactly once for the same refresh batch.");
  }
  await context.ensureHomeDepotBatchState("refresh-batch-two");
  if (removedCookies.length !== removalsBeforeBatchGuard + 10) {
    throw new Error("Expected a fresh Home Depot cleanup when the refresh batch changes.");
  }
  const reportFilename = context.reportDownloadFilename(
    { runId: 42, accountKey: "a.m.anim-59", reportType: "active_listings" },
    "eBay-all-active-listings-report.csv"
  );
  if (reportFilename !== "AutoZS/ebay-active-listings-a-m-anim-59-run-42.csv") {
    throw new Error(`Unexpected tagged report filename: ${reportFilename}`);
  }
  const trafficFilename = context.reportDownloadFilename(
    { runId: 43, accountKey: "a.m.anim-59", reportType: "traffic" },
    "active-listings-traffic.csv"
  );
  if (trafficFilename !== "AutoZS/ebay-traffic-a-m-anim-59-run-43.csv") {
    throw new Error(`Unexpected tagged traffic filename: ${trafficFilename}`);
  }
  await context.openNextProductCapture();
  const captureTab = createdTabs.find((tab) => /autozs_capture_product_id=44/.test(tab.url || ""));
  if (!captureTab || captureTab.active !== false || !/ea_auto_import=1/.test(captureTab.url)) {
    throw new Error(`Expected a background Home Depot capture runner, got ${JSON.stringify(createdTabs)}`);
  }
  const capturesBeforeQueuedRefresh = createdTabs.length;
  sourceRefreshJobs = [{ id: 756, status: "queued" }];
  await context.openNextProductCapture();
  if (createdTabs.length !== capturesBeforeQueuedRefresh) {
    throw new Error("Expected queued stock refresh work to take priority over product capture.");
  }
  storage.autozsSourceRefreshLastOpened = Date.now();
  storage.autozsProductCaptureLastOpened = 0;
  await context.openNextProductCapture();
  if (createdTabs.length !== capturesBeforeQueuedRefresh + 1) {
    throw new Error("Expected one product capture to use the source refresh cooldown window.");
  }
  sourceRefreshJobs = [];

  await context.uploadRevisionResultDownload(
    { batchId: 3, accountKey: "a.m.anim-59", filename: "result.csv" },
    { finalUrl: "https://www.ebay.com/result.csv", filename: "/Downloads/AutoZS/result.csv" }
  );
  const directImport = fetched.find((request) => request.url.endsWith("/ebay/revision-batches/3/results"));
  if (!directImport) throw new Error(`Expected direct revision result import, got ${JSON.stringify(fetched)}`);
  const directPayload = JSON.parse(directImport.options.body);
  if (directPayload.filename !== "result.csv" || !directPayload.result_base64) {
    throw new Error(`Unexpected direct revision payload: ${JSON.stringify(directPayload)}`);
  }
  await context.uploadTrafficReportDownload(
    { runId: 43, accountKey: "a.m.anim-59", filename: "traffic.csv" },
    { finalUrl: "https://www.ebay.com/traffic.csv", filename: "/Downloads/AutoZS/traffic.csv" }
  );
  const trafficImport = fetched.find((request) => request.url.endsWith("/stats/traffic/import-file"));
  if (!trafficImport) throw new Error(`Expected direct traffic report import, got ${JSON.stringify(fetched)}`);
  const trafficPayload = JSON.parse(trafficImport.options.body);
  if (trafficPayload.run_id !== 43 || trafficPayload.account_key !== "a.m.anim-59" || !trafficPayload.report_base64) {
    throw new Error(`Unexpected direct traffic payload: ${JSON.stringify(trafficPayload)}`);
  }

  let closeResponse = null;
  const closeReturned = listener(
    { type: "autozs-close-report-runner-tab", runId: 42 },
    { tab: { id: 11, url: "https://www.ebay.com/sh/reports/downloads#autozs_sync_run=42" } },
    (payload) => {
      closeResponse = payload;
    }
  );
  if (closeReturned !== true) throw new Error("Expected async close response marker.");
  if (closedTabs[0] !== 11 || !closeResponse?.ok) {
    throw new Error(`Expected report runner tab close, got tabs=${JSON.stringify(closedTabs)} response=${JSON.stringify(closeResponse)}`);
  }

  let sourceCloseResponse = null;
  const sourceCloseReturned = listener(
    { type: "autozs-close-source-refresh-tab", jobId: 756 },
    { tab: { id: 12, url: "https://www.homedepot.com/p/Test/123?ea_auto_import=1&autozs_refresh_job=756" } },
    (payload) => {
      sourceCloseResponse = payload;
    }
  );
  if (sourceCloseReturned !== true) throw new Error("Expected async source refresh close response marker.");
  if (!closedTabs.includes(12) || !sourceCloseResponse?.ok) {
    throw new Error(`Expected completed source refresh runner tab close, got tabs=${JSON.stringify(closedTabs)} response=${JSON.stringify(sourceCloseResponse)}`);
  }

  let response = null;
  const returned = listener(
    { type: "autozs-native-ebay-input", action: "replace-text", text: "PC text" },
    { tab: { id: 7, url: "https://www.ebay.com/lstng?draftId=123" } },
    (payload) => {
      response = payload;
    }
  );

  if (returned !== true) throw new Error("Expected async response marker from message listener.");
  await new Promise((resolve) => setImmediate(resolve));
  if (!response?.ok) throw new Error(`Expected successful native input response, got ${JSON.stringify(response)}`);

  const keyEvents = commands.filter((command) => command.method === "Input.dispatchKeyEvent").map((command) => command.params);
  if (keyEvents[0]?.key !== "Control" || keyEvents[0]?.code !== "ControlLeft") {
    throw new Error(`Expected PC Control keydown, got ${JSON.stringify(keyEvents[0])}`);
  }
  if (keyEvents[1]?.key !== "a" || keyEvents[1]?.modifiers !== 2) {
    throw new Error(`Expected Ctrl+A modifier 2, got ${JSON.stringify(keyEvents[1])}`);
  }
  if (keyEvents[3]?.key !== "Control" || keyEvents[3]?.code !== "ControlLeft") {
    throw new Error(`Expected PC Control keyup, got ${JSON.stringify(keyEvents[3])}`);
  }
  const insert = commands.find((command) => command.method === "Input.insertText");
  if (insert?.params?.text !== "PC text") {
    throw new Error(`Expected inserted text after Ctrl+A, got ${JSON.stringify(insert)}`);
  }

  commands.length = 0;
  response = null;
  listener(
    { type: "autozs-native-ebay-input", action: "type-text", text: "Hi" },
    { tab: { id: 7, url: "https://www.ebay.com/lstng?draftId=123" } },
    (payload) => { response = payload; }
  );
  await new Promise((resolve) => setImmediate(resolve));
  if (!response?.ok) throw new Error(`Expected successful native typing response, got ${JSON.stringify(response)}`);
  const typedKeys = commands.filter((command) => command.method === "Input.dispatchKeyEvent").map((command) => command.params);
  if (typedKeys.length !== 4 || typedKeys[0]?.key !== "H" || typedKeys[2]?.key !== "i") {
    throw new Error(`Expected per-character native key events, got ${JSON.stringify(typedKeys)}`);
  }

  commands.length = 0;
  response = null;
  listener(
    { type: "autozs-native-ebay-input", action: "commit-text" },
    { tab: { id: 7, url: "https://www.ebay.com/lstng?draftId=123" } },
    (payload) => { response = payload; }
  );
  await new Promise((resolve) => setImmediate(resolve));
  const commitKeys = commands.filter((command) => command.method === "Input.dispatchKeyEvent").map((command) => command.params);
  if (!response?.ok || commitKeys.length !== 2 || commitKeys.some((event) => event.key !== "Tab")) {
    throw new Error(`Expected native Tab commit, got response=${JSON.stringify(response)} events=${JSON.stringify(commitKeys)}`);
  }

  commands.length = 0;
  context.navigator.platform = "MacIntel";
  await context.replaceFocusedText((method, params) => {
    commands.push({ method, params });
    return Promise.resolve();
  }, "Mac text");
  const macKeyEvents = commands.filter((command) => command.method === "Input.dispatchKeyEvent").map((command) => command.params);
  if (macKeyEvents[0]?.key !== "Meta" || macKeyEvents[0]?.code !== "MetaLeft") {
    throw new Error(`Expected Mac Meta keydown, got ${JSON.stringify(macKeyEvents[0])}`);
  }
  if (macKeyEvents[1]?.key !== "a" || macKeyEvents[1]?.modifiers !== 4) {
    throw new Error(`Expected Command+A modifier 4, got ${JSON.stringify(macKeyEvents[1])}`);
  }
  const macInsert = commands.find((command) => command.method === "Input.insertText");
  if (macInsert?.params?.text !== "Mac text") {
    throw new Error(`Expected inserted text after Command+A, got ${JSON.stringify(macInsert)}`);
  }

  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsWorkerMode = "operations";
  storage.autozsEbayRevisionLastOpened = 0;
  await context.openNextEbayRevisionJob();
  if (fetched.some((request) => request.url.endsWith("/ebay/revision-jobs/next"))) {
    throw new Error(`Expected Mac platform to skip revision queue claim, got ${JSON.stringify(fetched)}`);
  }
  if (createdTabs.length !== 0) {
    throw new Error(`Expected Mac platform to avoid opening worker tabs, got ${JSON.stringify(createdTabs)}`);
  }

  context.navigator.platform = "Win32";
  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsWorkerMode = "operations";
  storage.autozsListingJobLastOpened = 0;
  await context.openNextListingJob();
  if (!fetched.some((request) => request.url.endsWith("/listing-jobs/next") && request.options.method === "POST")) {
    throw new Error(`Expected listing queue claim, got ${JSON.stringify(fetched)}`);
  }
  if (createdTabs.length !== 1 || !context.isListingJobRunnerUrl(createdTabs[0].url, 92)) {
    throw new Error(`Expected one background eBay listing tab, got ${JSON.stringify(createdTabs)}`);
  }
  await context.openNextListingJob();
  if (createdTabs.length !== 1) throw new Error("Expected listing poll throttle to prevent duplicate tabs.");

  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsListingJobLastOpened = 0;
  runningListingJobs = [{
    id: 77,
    status: "running",
    assistant_url: "https://www.ebay.com/lstng?draftId=abc&autozs_job_id=77#autozs_job_id=77",
  }];
  tabQueryResults = [];
  await context.openNextListingJob();
  if (fetched.some((request) => request.url.endsWith("/listing-jobs/next"))) {
    throw new Error("Expected no new claim while a job is already running.");
  }
  if (createdTabs.length !== 1 || !context.isListingJobRunnerUrl(createdTabs[0].url, 77)) {
    throw new Error(`Expected the orphaned running job runner to reopen, got ${JSON.stringify(createdTabs)}`);
  }

  createdTabs.length = 0;
  storage.autozsListingJobLastOpened = 0;
  tabQueryResults = [{ id: 9, url: "https://www.ebay.com/lstng?draftId=abc&autozs_job_id=77" }];
  await context.openNextListingJob();
  if (createdTabs.length !== 0) {
    throw new Error(`Expected no reopen while the runner tab is alive, got ${JSON.stringify(createdTabs)}`);
  }

  // Regression: a runner that reported progress seconds ago is alive by
  // definition, whatever chrome.tabs reports. Reopening restarts the workflow
  // from the top and the description step runs near the end, so a job that is
  // mid-fill never survives to write one -- then reports it could not. Seen live
  // on job 106: recovery 1/3, recovery 2/3, a liveness ping proving the content
  // script was working, then recovery 3/3 stacked on top of it.
  const quietJob = {
    id: 77,
    status: "running",
    assistant_url: "https://www.ebay.com/lstng?draftId=abc&autozs_job_id=77#autozs_job_id=77",
  };
  createdTabs.length = 0;
  storage.autozsListingJobLastOpened = 0;
  storage.autozsListingJobReopens = { "77": 3 };
  storage.autozsListingJobRunnerTabs = {};
  tabQueryResults = [];
  runningListingJobs = [{
    ...quietJob,
    updated_at: new Date(Date.now() - 30 * 1000).toISOString().replace("Z", ""),
  }];
  await context.openNextListingJob();
  if (createdTabs.length !== 0) {
    throw new Error(
      `Expected no reopen for a runner that reported progress 30s ago, got ${JSON.stringify(createdTabs)}`
    );
  }

  // A fresh API reservation has started_at and updated_at written together but
  // no browser tab yet. It must open even though its timestamp is recent.
  createdTabs.length = 0;
  storage.autozsListingJobLastOpened = 0;
  storage.autozsListingJobReopens = { "77": 3 };
  storage.autozsListingJobRunnerTabs = {};
  tabQueryResults = [];
  const reservedAt = new Date(Date.now() - 10 * 1000).toISOString().replace("Z", "");
  runningListingJobs = [{
    ...quietJob,
    started_at: reservedAt,
    updated_at: reservedAt,
    message: "Reserved for scheduled eBay publishing",
  }];
  await context.openNextListingJob();
  if (createdTabs.length !== 1) {
    throw new Error(`Expected a freshly reserved job with no runner tab to open, got ${JSON.stringify(createdTabs)}`);
  }

  // ...but a runner that has genuinely gone quiet must still be recovered.
  createdTabs.length = 0;
  storage.autozsListingJobLastOpened = 0;
  storage.autozsListingJobReopens = {};
  storage.autozsListingJobRunnerTabs = {};
  tabQueryResults = [];
  runningListingJobs = [{
    ...quietJob,
    updated_at: new Date(Date.now() - 20 * 60 * 1000).toISOString().replace("Z", ""),
  }];
  await context.openNextListingJob();
  if (createdTabs.length !== 1) {
    throw new Error(
      `Expected a silent orphaned runner to still be reopened, got ${JSON.stringify(createdTabs)}`
    );
  }
  runningListingJobs = [quietJob];

  // A runner that has navigated on to the editor no longer carries
  // autozs_job_id; it must still count as alive or a second tab gets opened
  // and the two runners corrupt each other's draft.
  createdTabs.length = 0;
  storage.autozsListingJobLastOpened = 0;
  tabQueryResults = [{ id: 12, url: "https://www.ebay.com/lstng?draftId=5351561921310&mode=AddItem" }];
  await context.openNextListingJob();
  if (createdTabs.length !== 0) {
    throw new Error(`Expected an editor tab without autozs params to count as a live runner, got ${JSON.stringify(createdTabs)}`);
  }

  createdTabs.length = 0;
  reloadedTabs.length = 0;
  storage.autozsListingJobLastOpened = 0;
  tabQueryResults = [{ id: 9, url: "https://www.ebay.com/lstng?draftId=abc&autozs_job_id=77", discarded: true }];
  await context.openNextListingJob();
  if (reloadedTabs.length !== 1 || reloadedTabs[0] !== 9 || createdTabs.length !== 0) {
    throw new Error(`Expected a discarded runner tab to be reloaded, got ${JSON.stringify({ reloadedTabs, createdTabs })}`);
  }
  // A reopened runner must refresh the job so the API's 30-minute watchdog
  // stops flagging recovered jobs as "worker stopped reporting", and must give
  // up after a few tries so a hopeless job still fails.
  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsListingJobLastOpened = 0;
  storage.autozsListingJobReopens = {};
  runningListingJobs = [{
    id: 77,
    status: "running",
    assistant_url: "https://www.ebay.com/lstng?draftId=abc&autozs_job_id=77#autozs_job_id=77",
  }];
  tabQueryResults = [];
  await context.openNextListingJob();
  const heartbeat = fetched.find(
    (request) => request.url.endsWith("/listing-jobs/77") && request.options.method === "PATCH"
  );
  if (!heartbeat || !/reopened by AutoZS/.test(String(heartbeat.options.body))) {
    throw new Error(`Expected a heartbeat PATCH for the reopened job, got ${JSON.stringify(fetched.map((f) => f.url))}`);
  }
  if (storage.autozsListingJobReopens["77"] !== 1) {
    throw new Error(`Expected the reopen count to be tracked, got ${JSON.stringify(storage.autozsListingJobReopens)}`);
  }

  createdTabs.length = 0;
  storage.autozsListingJobLastOpened = 0;
  storage.autozsListingJobReopens = { "77": 3 };
  await context.openNextListingJob();
  if (createdTabs.length !== 0) {
    throw new Error(`Expected reopen attempts to stop after 3 tries, got ${JSON.stringify(createdTabs)}`);
  }

  runningListingJobs = [];
  tabQueryResults = [];

  const closedBeforeFreshListingRunner = closedTabs.length;
  createdTabs.length = 0;
  tabQueryResults = [{
    id: 44,
    url: "https://www.ebay.com/lstng?draftId=old&autozs_job_id=91",
  }, {
    id: 45,
    url: "https://www.ebay.com/lstng?draftId=restored-without-job-param",
  }];
  await context.openListingJobRunner({
    job: {
      id: 92,
      assistant_url: "https://www.ebay.com/sl/prelist/home?autozs_job_id=92#autozs_job_id=92",
    },
    package: { title: "Fresh listing" },
  });
  const closedForFreshListingRunner = closedTabs.slice(closedBeforeFreshListingRunner);
  if (!closedForFreshListingRunner.includes(44) || !closedForFreshListingRunner.includes(45) || createdTabs.length !== 1) {
    throw new Error(`Expected all stale listing workflow tabs to close before opening a fresh tab, got ${JSON.stringify({ closedTabs, createdTabs })}`);
  }
  tabQueryResults = [];

  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsWorkerMode = "operations";
  storage.autozsCustomerMessageLastOpened = 0;
  await context.openNextCustomerMessage();
  if (!fetched.some((request) => request.url.endsWith("/customer-service/messages/next") && request.options.method === "POST")) {
    throw new Error(`Expected customer-message queue claim, got ${JSON.stringify(fetched)}`);
  }
  if (
    createdTabs.length !== 1 ||
    !context.isCustomerMessageRunnerUrl(createdTabs[0].url, 5) ||
    !createdTabs[0].active
  ) {
    throw new Error(`Expected one active eBay customer-message tab, got ${JSON.stringify(createdTabs)}`);
  }
  const messageUrl = new URL(createdTabs[0].url);
  // The Orders list filtered to this order's ID is the target that actually
  // resolves -- ebay.com/sh/ord/details regularly fails to load at all.
  if (messageUrl.pathname !== "/sh/ord" || messageUrl.searchParams.get("q") !== "13-14947-26719") {
    throw new Error(`Expected the Orders list filtered to this order ID in the message runner URL, got ${createdTabs[0].url}`);
  }
  if (storage.autozsCustomerMessagePayloads?.["5"]?.message?.body !== "English and Spanish refund message") {
    throw new Error(`Expected queued message payload in extension storage, got ${JSON.stringify(storage.autozsCustomerMessagePayloads)}`);
  }
  tabQueryResults = [];

  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsWorkerMode = "checkout";
  storage.autozsSupplierOrderLastOpened = 0;
  tabQueryResults = [{ id: 77, url: "https://www.homedepot.com/cart", title: "Error Page" }];
  await context.openNextSupplierOrder();
  if (fetched.some((request) => request.url.endsWith("/supplier-orders/next"))) {
    throw new Error("Expected Home Depot's Error Page to prevent a supplier-order claim during cooldown.");
  }
  if (!(Number(storage.autozsSupplierCheckoutBlockedUntil || 0) > Date.now())) {
    throw new Error("Expected Home Depot checkout cooldown to persist in extension storage.");
  }
  tabQueryResults = [];
  storage.autozsSupplierCheckoutBlockedUntil = 0;
  await context.openNextSupplierOrder();
  if (!fetched.some((request) => request.url.endsWith("/supplier-orders/next") && request.options.method === "POST")) {
    throw new Error(`Expected supplier-order queue claim, got ${JSON.stringify(fetched)}`);
  }
  if (createdTabs.length !== 1 || !context.isSupplierOrderRunnerUrl(createdTabs[0].url, 14)) {
    throw new Error(`Expected one guarded Home Depot checkout tab, got ${JSON.stringify(createdTabs)}`);
  }
  const checkoutUrl = new URL(createdTabs[0].url);
  if (checkoutUrl.searchParams.get("autozs_checkout_canary") !== "1") {
    throw new Error(`Expected checkout canary marker, got ${createdTabs[0].url}`);
  }
  const tokens = storage.autozsSupplierCheckoutTokens || {};
  if (tokens["14"]?.token !== "checkout-token-14") {
    throw new Error(`Expected short-lived checkout token to be retained by the service worker, got ${JSON.stringify(tokens)}`);
  }
  tabQueryResults = [];

  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsWorkerMode = "operations";
  storage.autozsEbayRevisionLastOpened = 0;
  await context.openNextEbayRevisionJob();
  if (!fetched.some((request) => request.url.endsWith("/ebay/revision-jobs/next") && request.options.method === "POST")) {
    throw new Error(`Expected revision queue claim, got ${JSON.stringify(fetched)}`);
  }
  if (createdTabs.length !== 1 || !context.isEbayRevisionRunnerUrl(createdTabs[0].url, 91)) {
    throw new Error(`Expected one background eBay revision tab, got ${JSON.stringify(createdTabs)}`);
  }
  await context.openNextEbayRevisionJob();
  if (createdTabs.length !== 1) throw new Error("Expected revision poll throttle to prevent duplicate tabs.");

  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsWorkerMode = "viewer";
  storage.autozsEbayRevisionLastOpened = 0;
  await context.openNextEbayRevisionJob();
  if (fetched.some((request) => request.url.endsWith("/ebay/revision-jobs/next"))) {
    throw new Error(`Expected viewer mode to skip revision queue claim, got ${JSON.stringify(fetched)}`);
  }
  if (createdTabs.length !== 0) {
    throw new Error(`Expected viewer mode to avoid opening worker tabs, got ${JSON.stringify(createdTabs)}`);
  }

  storage.autozsWorkerMode = "viewer";
  storage.autozsHomeDepotSourceWorkerPaused = true;
  storage.autozsHomeDepotPostCleanupErrors = 3;
  tabQueryResults = [{ url: "https://desktop-56u49jf.tailb2892a.ts.net/?autozs_worker_mode=operations" }];
  const recoveredMode = await context.syncRequestedWorkerModeFromDashboardTabs();
  if (
    recoveredMode !== "operations" ||
    storage.autozsWorkerMode !== "operations" ||
    storage.autozsHomeDepotSourceWorkerPaused !== false ||
    storage.autozsHomeDepotPostCleanupErrors !== 0
  ) {
    throw new Error(`Expected an explicit operations dashboard URL to clear stale source failover state, got ${JSON.stringify(storage)}`);
  }
  return context;
}

if (!source.includes('["operations", "capture", "checkout", "viewer"].includes(mode)')) {
  throw new Error("Expected the dashboard bridge to allow the dedicated checkout worker mode.");
}
if (!source.includes("syncRequestedWorkerModeFromDashboardTabs")) {
  throw new Error("Expected worker mode to be recoverable directly from a dashboard tab at Chrome startup.");
}
if (!source.includes('message?.type === "autozs-supplier-checkout-api"')) {
  throw new Error("Expected Home Depot checkout reads and updates to use the trusted background broker.");
}
if (!source.includes('message?.type === "autozs-supplier-tracking-observation"')) {
  throw new Error("Expected Home Depot shipment observations to use the trusted background broker.");
}
if (!source.includes('message?.type === "autozs-supplier-tracking-blocked"')) {
  throw new Error("Expected rendered Home Depot error pages to trigger tracking cooldown through the trusted broker.");
}
if (!source.includes('parsed.searchParams.get("orderId") === String(externalOrderId || "")')) {
  throw new Error("Expected shipment reconciliation to require an exact Home Depot order ID in the page URL.");
}
if (!source.includes('matches.length !== 1')) {
  throw new Error("Expected shipment reconciliation to require exactly one matching AUTOZS supplier order.");
}
if (!source.includes('[SUPPLIER_TRACKING_ALARM, 5, 360]')) {
  throw new Error("Expected Home Depot tracking checks to run no more than once every six hours.");
}
if (!source.includes('SUPPLIER_TRACKING_ERROR_COOLDOWN_MS = 24 * 60 * 60 * 1000')) {
  throw new Error("Expected Home Depot anti-automation responses to pause tracking checks for 24 hours.");
}
if (!source.includes('await chrome.tabs.create({ url: supplierTrackingRunnerUrl(eligible[0]), active: false })')) {
  throw new Error("Expected tracking polling to open only one inactive Home Depot order tab.");
}
if (!source.includes('localApiJson("/supplier-orders/ebay-tracking-next")')) {
  throw new Error("Expected the eBay tracking opener to consume only the guarded API handoff.");
}
if (!source.includes('message?.type === "autozs-ebay-tracking-candidate"')) {
  throw new Error("Expected tracking form preparation to revalidate its handoff through the trusted broker.");
}
if (!source.includes('message?.type === "autozs-ebay-tracking-prepared"')) {
  throw new Error("Expected a verified tracking form to record a local prepared-state fingerprint.");
}
if (!source.includes('message?.type === "autozs-ebay-tracking-submitted"')) {
  throw new Error("Expected confirmed eBay tracking to queue authoritative order reconciliation.");
}
if (!source.includes('/orders/sync?account_key=${encodeURIComponent(accountKey)}')) {
  throw new Error("Expected tracking confirmation to force an eBay order re-sync for the exact account.");
}
if (!source.includes('prepared[String(candidate.supplier_order_id)] === fingerprint')) {
  throw new Error("Expected an unchanged prepared tracking form not to reopen repeatedly.");
}
if (!source.includes('candidate.ebay_order_id !== page.searchParams.get("q")')) {
  throw new Error("Expected the tracking broker to require the exact eBay order ID shown in the marked tab.");
}
if (!source.includes('await chrome.tabs.create({ url: ebayTrackingUploadRunnerUrl(candidate), active: false })')) {
  throw new Error("Expected the eBay tracking candidate to open in one inactive tab.");
}
if (!source.includes('parsed.searchParams.get("autozs_workflow") === "tracking_upload"')) {
  throw new Error("Expected eBay tracking tabs to carry an exact workflow identity.");
}
if (!source.includes('(!isSupplierOrderRunnerUrl(url) && !isSupplierTrackingRunnerUrl(url))')) {
  throw new Error("Expected explicit content-script injection to be narrowly allowed on marked tracking tabs.");
}
if (!source.includes('message?.type === "autozs-supplier-native-click"')) {
  throw new Error("Expected guarded supplier actions to use trusted native clicks.");
}
if (!source.includes('continue: "^continue$"')) {
  throw new Error("Expected the guarded checkout allow-list to support Continue without supporting Place Order.");
}
if (!source.includes('remove_from_cart: "^remove$"')) {
  throw new Error("Expected cart recovery to allow only an exact Home Depot Remove button.");
}
if (!source.includes('message?.type === "autozs-supplier-native-fill"')) {
  throw new Error("Expected guarded checkout fields to use trusted native input.");
}
if (!source.includes('if (typeof field.select === "function") field.select()')) {
  throw new Error("Expected native checkout entry to replace the complete existing field value.");
}

function runCustomerMessageRunnerUrlTest(context) {
  // The Orders LIST page filtered to this order's ID is the one target that
  // resolves reliably (order-details deep links regularly fail to load at
  // all, independent of which ID gets passed). This needs only the order ID
  // string that's always present -- no Sales Record Number required.
  const withOrder = context.customerMessageRunnerUrl(
    { id: 5 },
    { ebay_thread_id: "order:22-15024-78151" }
  );
  const withOrderUrl = new URL(withOrder);
  if (withOrderUrl.pathname !== "/sh/ord" || withOrderUrl.searchParams.get("q") !== "22-15024-78151") {
    throw new Error(`Expected the Orders list filtered to this order ID, got ${withOrder}`);
  }

  // Without a resolvable order ID at all, fall back to the general inbox.
  const withoutOrder = context.customerMessageRunnerUrl({ id: 5 }, { ebay_thread_id: "" });
  if (!withoutOrder.startsWith("https://www.ebay.com/mys/messages")) {
    throw new Error(`Expected a fallback to the eBay inbox, got ${withoutOrder}`);
  }
}

runNativePcInputTest()
  .then((context) => {
    runCustomerMessageRunnerUrlTest(context);
    console.log("background native PC input tests ok");
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
