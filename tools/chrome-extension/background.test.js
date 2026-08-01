const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/background.js`, "utf8");

async function runNativePcInputTest() {
  let listener = null;
  const commands = [];
  const closedTabs = [];
  const createdTabs = [];
  const removedCookies = [];
  const browsingDataRemovals = [];
  let tabQueryResults = [];
  let runningListingJobs = [];
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
  storage.autozsListingJobReopens = {};
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
  }];
  await context.openListingJobRunner({
    job: {
      id: 92,
      assistant_url: "https://www.ebay.com/sl/prelist/home?autozs_job_id=92#autozs_job_id=92",
    },
    package: { title: "Fresh listing" },
  });
  if (closedTabs[closedBeforeFreshListingRunner] !== 44 || createdTabs.length !== 1) {
    throw new Error(`Expected a stale listing runner to close before opening a fresh tab, got ${JSON.stringify({ closedTabs, createdTabs })}`);
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
  if (messageUrl.searchParams.get("srn") !== "13-14947-26719") {
    throw new Error(`Expected the eBay order number in the message runner URL, got ${createdTabs[0].url}`);
  }
  if (storage.autozsCustomerMessagePayloads?.["5"]?.message?.body !== "English and Spanish refund message") {
    throw new Error(`Expected queued message payload in extension storage, got ${JSON.stringify(storage.autozsCustomerMessagePayloads)}`);
  }
  tabQueryResults = [];

  createdTabs.length = 0;
  fetched.length = 0;
  storage.autozsWorkerMode = "operations";
  storage.autozsSupplierOrderLastOpened = 0;
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
}

runNativePcInputTest()
  .then(() => console.log("background native PC input tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
