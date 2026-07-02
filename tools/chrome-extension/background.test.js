const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/background.js`, "utf8");

async function runNativePcInputTest() {
  let listener = null;
  const commands = [];
  const closedTabs = [];
  const context = {
    console,
    URL,
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
      tabs: {
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
}

runNativePcInputTest()
  .then(() => console.log("background native PC input tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
