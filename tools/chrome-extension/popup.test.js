const fs = require("fs");
const vm = require("vm");

const source = `${fs.readFileSync(`${__dirname}/capture.js`, "utf8")}\n${fs.readFileSync(`${__dirname}/popup.js`, "utf8")}`;

function popupElements() {
  const listeners = {};
  const elements = {
    status: { textContent: "" },
    "connection-status": { dataset: {} },
    "connection-label": { textContent: "" },
    "ebay-product-id": { dataset: {}, textContent: "" },
    capture: {},
    "show-ebay-assistant": { textContent: "Show eBay Assistant" },
    "open-dashboard": {},
  };
  for (const [id, element] of Object.entries(elements)) {
    element.addEventListener = (event, handler) => {
      listeners[`${id}:${event}`] = handler;
    };
  }
  return { elements, listeners };
}

async function runPopupAssistantToggleTest() {
  const { elements } = popupElements();
  const injected = [];
  let assistantVisible = false;
  const context = {
    console,
    URL,
    fetch: async (url) => {
      if (String(url).endsWith("/settings")) return { ok: true, json: async () => ({ ui_theme: "light" }) };
      if (String(url).endsWith("/health")) return { ok: true, json: async () => ({ status: "ok" }) };
      if (String(url).endsWith("/ebay/browser-account")) {
        return { ok: true, json: async () => ({ can_list: true, message: "Chrome eBay account matches autozs-seller." }) };
      }
      throw new Error(`Unexpected fetch ${url}`);
    },
    window: { matchMedia: () => ({ matches: false }) },
    document: {
      body: { dataset: {} },
      getElementById: (id) => elements[id],
    },
    chrome: {
      tabs: {
        query: async () => [{ id: 7, url: "https://www.ebay.com/lstng?draftId=123&mode=AddItem#autozs_popup_product_id=40" }],
        create: async () => {},
      },
      scripting: {
        executeScript: async (payload) => {
          injected.push(payload);
          if (payload.func?.name === "detectEbaySignedInUsernameFromPage") return [{ result: "autozs-seller" }];
          if (payload.files) {
            assistantVisible = true;
            return [{ result: null }];
          }
          if (!payload.args) {
            const wasVisible = assistantVisible;
            assistantVisible = false;
            return [{ result: { wasVisible } }];
          }
          return [{ result: null }];
        },
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise((resolve) => setTimeout(resolve, 0));

  if (elements["connection-label"].textContent !== "Live") {
    throw new Error(`Expected automatic Live status, got ${elements["connection-label"].textContent}`);
  }

  await vm.runInContext("showEbayAssistant()", context);
  if (!assistantVisible || elements["show-ebay-assistant"].textContent !== "Hide eBay Assistant") {
    throw new Error("Expected the assistant to open and the button to switch to Hide.");
  }
  if (JSON.stringify(injected.at(-1).files) !== JSON.stringify(["capture.js", "ebay-fill.js"])) {
    throw new Error(`Expected capture and assistant files to be injected, got ${JSON.stringify(injected.at(-1).files)}`);
  }

  await vm.runInContext("showEbayAssistant()", context);
  if (assistantVisible || elements["show-ebay-assistant"].textContent !== "Show eBay Assistant") {
    throw new Error("Expected the assistant to hide and the button to switch to Show.");
  }
  if (!elements.status.textContent.includes("hidden")) {
    throw new Error(`Expected hidden status, got ${elements.status.textContent}`);
  }
}

async function runPopupAccountFallbackTest() {
  const { elements } = popupElements();
  const calls = [];
  const context = {
    console,
    URL,
    encodeURIComponent,
    fetch: async (url) => {
      calls.push(String(url));
      if (String(url).endsWith("/settings")) return { ok: true, json: async () => ({ ui_theme: "light" }) };
      if (String(url).endsWith("/health")) return { ok: true, json: async () => ({ status: "ok" }) };
      if (String(url).includes("/ebay/browser-account?account_key=main-store")) {
        return { ok: true, json: async () => ({ can_list: true, detected_username: "a.m.anim-59" }) };
      }
      throw new Error(`Unexpected fetch ${url}`);
    },
    window: { matchMedia: () => ({ matches: false }) },
    document: {
      body: { dataset: {} },
      getElementById: (id) => elements[id],
    },
    chrome: {
      tabs: {
        query: async () => [{ id: 7, url: "https://www.ebay.com/itm/318496463400" }],
        create: async () => {},
      },
      scripting: {
        executeScript: async (payload) => {
          if (payload.func?.name === "detectEbaySignedInUsernameFromPage") return [{ result: "" }];
          return [{ result: null }];
        },
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  const status = await vm.runInContext('refreshEbayBrowserAccountFromActiveTab("main-store")', context);
  if (status.detected_username !== "a.m.anim-59") {
    throw new Error(`Expected existing account fallback, got ${JSON.stringify(status)}`);
  }
  if (calls.some((url) => url.endsWith("/ebay/browser-account"))) {
    throw new Error(`Expected no blank browser-account POST, got ${JSON.stringify(calls)}`);
  }
}

runPopupAssistantToggleTest()
  .then(runPopupAccountFallbackTest)
  .then(() => console.log("popup eBay assistant toggle and account fallback tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
