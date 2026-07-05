const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/background.js`, "utf8");

async function runNativePcInputTest() {
  let listener = null;
  const commands = [];
  const closedTabs = [];
  const createdTabs = [];
  const storage = { autozsWorkerMode: "operations" };
  const fetched = [];
  const context = {
    console,
    URL,
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
        query: async () => [],
        create: async (options) => {
          createdTabs.push(options);
          return { id: 23, ...options };
        },
        update: async () => {},
        remove: (tabId, callback) => {
          closedTabs.push(tabId);
          callback?.();
        },
      },
    },
    navigator: { platform: "Win32" },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  if (!listener) throw new Error("Expected background message listener to be registered.");
  const reportFilename = context.reportDownloadFilename(
    { runId: 42, accountKey: "Main Store", reportType: "active_listings" },
    "eBay-all-active-listings-report.csv"
  );
  if (reportFilename !== "AutoZS/ebay-active-listings-main-store-run-42.csv") {
    throw new Error(`Unexpected tagged report filename: ${reportFilename}`);
  }

  await context.uploadRevisionResultDownload(
    { batchId: 3, accountKey: "main-store", filename: "result.csv" },
    { finalUrl: "https://www.ebay.com/result.csv", filename: "/Downloads/AutoZS/result.csv" }
  );
  const directImport = fetched.find((request) => request.url.endsWith("/ebay/revision-batches/3/results"));
  if (!directImport) throw new Error(`Expected direct revision result import, got ${JSON.stringify(fetched)}`);
  const directPayload = JSON.parse(directImport.options.body);
  if (directPayload.filename !== "result.csv" || !directPayload.result_base64) {
    throw new Error(`Unexpected direct revision payload: ${JSON.stringify(directPayload)}`);
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
