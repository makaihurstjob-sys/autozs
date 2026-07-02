const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/content.js`, "utf8");

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.parentNode = null;
    this.previousElementSibling = null;
    this.style = { cssText: "", setProperty: (key, value) => { this.style[key] = value; } };
  }

  attachShadow() {
    this.shadowRoot = {
      innerHTML: "",
      querySelector: (selector) => {
        if (selector === "button") return { disabled: false, addEventListener: () => {} };
        if (selector === ".status") return { textContent: "", title: "" };
        return null;
      },
    };
    return this.shadowRoot;
  }

  insertAdjacentElement(position, element) {
    if (position !== "afterend") throw new Error(`Unexpected position: ${position}`);
    element.parentNode = this.parentNode;
    element.previousElementSibling = this;
    this.parentNode.hosted = element;
  }

  append(element) {
    element.parentNode = this;
    element.previousElementSibling = this.children[this.children.length - 1] || null;
    this.children.push(element);
    this.hosted = element;
  }
}

async function runContentTest() {
  const body = new FakeElement("body");
  const purchasePanel = new FakeElement("section");
  purchasePanel.parentNode = body;
  let mutationCallback = null;

  body.prepend = (element) => {
    element.parentNode = body;
    element.previousElementSibling = null;
    body.hosted = element;
  };

  const context = {
    console,
    URLSearchParams,
    setInterval: () => 1,
    clearInterval: () => {},
    MutationObserver: class {
      constructor(callback) {
        mutationCallback = callback;
      }
      observe() {}
      disconnect() {}
    },
    window: {
      __ebayAutomationImportButton: false,
      addEventListener: () => {},
    },
    location: { search: "" },
    document: {
      body,
      hidden: false,
      createElement: (tagName) => new FakeElement(tagName),
      addEventListener: () => {},
      getElementById: (id) => (purchasePanel.hosted && purchasePanel.hosted.id === id ? purchasePanel.hosted : null),
      querySelector: (selector) => (selector.includes("buybox") ? purchasePanel : null),
    },
    readAppTheme: async () => "dark",
    checkLocalApi: async () => ({ status: "ok" }),
    captureSourceProductFromPage: () => ({}),
    importCapturedProduct: async () => ({ sku: "TEST", images: [] }),
    downloadProductImages: async () => ({ downloaded: 0, attempted: 0 }),
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));

  if (!purchasePanel.hosted || purchasePanel.hosted.parentNode !== purchasePanel) {
    throw new Error("Expected the import action to mount inside the purchase panel.");
  }

  mutationCallback();

  if (purchasePanel.hosted.parentNode !== purchasePanel) {
    throw new Error("Expected the import action to remain in the purchase panel after mutations.");
  }
}

async function runAutoImportTest() {
  const body = new FakeElement("body");
  let imported = 0;

  body.prepend = (element) => {
    element.parentNode = body;
    element.previousElementSibling = null;
    body.hosted = element;
  };

  const context = {
    console,
    URLSearchParams,
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: (callback) => {
      callback();
      return 1;
    },
    MutationObserver: class {
      observe() {}
      disconnect() {}
    },
    window: {
      __ebayAutomationImportButton: false,
      __ebayAutomationAutoImportStarted: false,
      addEventListener: () => {},
    },
    location: { search: "?ea_auto_import=1" },
    document: {
      body,
      hidden: false,
      createElement: (tagName) => new FakeElement(tagName),
      addEventListener: () => {},
      getElementById: (id) => (body.hosted && body.hosted.id === id ? body.hosted : null),
      querySelector: () => null,
    },
    readAppTheme: async () => "light",
    checkLocalApi: async () => ({ status: "ok" }),
    captureSourceProductFromPage: () => ({
      source_url: "https://www.homedepot.com/p/Test/123",
      title: "Ready Product",
      source_price: 17.97,
      detected_shipping: 0,
      image_urls: "https://images.thdstatic.com/productImages/ready-front.jpg",
    }),
    importCapturedProduct: async (payload) => {
      imported += 1;
      if (payload.detected_shipping !== undefined) throw new Error("detected_shipping should be stripped before import");
      if (payload.source_shipping !== 0) throw new Error("detected shipping should become source_shipping");
      return { sku: "TEST", images: [] };
    },
    downloadProductImages: async () => ({ downloaded: 0, attempted: 0 }),
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));

  if (imported !== 1) {
    throw new Error(`Expected auto import to run once, got ${imported}`);
  }
}

async function runDelayedCaptureTest() {
  const body = new FakeElement("body");
  let captureCalls = 0;
  let importedPayload = null;

  body.prepend = (element) => {
    element.parentNode = body;
    element.previousElementSibling = null;
    body.hosted = element;
  };

  const context = {
    console,
    URLSearchParams,
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: (callback) => {
      callback();
      return 1;
    },
    MutationObserver: class {
      observe() {}
      disconnect() {}
    },
    window: {
      __ebayAutomationImportButton: false,
      __ebayAutomationAutoImportStarted: false,
      addEventListener: () => {},
    },
    location: { search: "?ea_auto_import=1" },
    document: {
      body,
      hidden: false,
      createElement: (tagName) => new FakeElement(tagName),
      addEventListener: () => {},
      getElementById: (id) => (body.hosted && body.hosted.id === id ? body.hosted : null),
      querySelector: () => null,
    },
    readAppTheme: async () => "light",
    checkLocalApi: async () => ({ status: "ok" }),
    captureSourceProductFromPage: () => {
      captureCalls += 1;
      if (captureCalls < 3) {
        return { source_url: "https://www.homedepot.com/p/Test/123", title: "Home Depot", source_price: null, image_urls: "" };
      }
      return {
        source_url: "https://www.homedepot.com/p/Test/123",
        title: "Hydrated Product",
        source_price: 22.25,
        detected_shipping: 0,
        image_urls: "https://images.thdstatic.com/productImages/hydrated-front.jpg",
      };
    },
    importCapturedProduct: async (payload) => {
      importedPayload = payload;
      return { sku: "TEST", images: [] };
    },
    downloadProductImages: async () => ({ downloaded: 0, attempted: 0 }),
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));

  if (captureCalls !== 3) {
    throw new Error(`Expected capture to wait for hydration, got ${captureCalls} call(s)`);
  }
  if (!importedPayload || importedPayload.title !== "Hydrated Product" || importedPayload.source_price !== 22.25) {
    throw new Error(`Expected hydrated payload to import, got ${JSON.stringify(importedPayload)}`);
  }
}

async function runSourceRefreshPacingTest() {
  const body = new FakeElement("body");
  const delays = [];
  let imageDownloads = 0;
  let nextClaims = 0;

  body.prepend = (element) => {
    element.parentNode = body;
    body.hosted = element;
  };

  const context = {
    console,
    URLSearchParams,
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: (callback, delay = 0) => {
      delays.push(delay);
      if (delay < 45 * 1000) callback();
      return 1;
    },
    MutationObserver: class {
      observe() {}
      disconnect() {}
    },
    window: {
      __ebayAutomationImportButton: false,
      __ebayAutomationAutoImportStarted: false,
      addEventListener: () => {},
    },
    location: { search: "?ea_auto_import=1&autozs_refresh_job=7&autozs_refresh_batch=batch-1", replace: () => {} },
    document: {
      body,
      hidden: false,
      createElement: (tagName) => new FakeElement(tagName),
      addEventListener: () => {},
      getElementById: (id) => (body.hosted && body.hosted.id === id ? body.hosted : null),
      querySelector: () => null,
    },
    readAppTheme: async () => "light",
    checkLocalApi: async () => ({ status: "ok" }),
    sourceRefreshContextFromLocation: () => ({ jobId: 7, batchKey: "batch-1" }),
    captureSourceProductFromPage: () => ({
      source_url: "https://www.homedepot.com/p/Test/123",
      title: "Refresh Product",
      source_price: 19.99,
      detected_shipping: 0,
      image_urls: "https://images.thdstatic.com/productImages/refresh-front.jpg",
    }),
    importCapturedProduct: async () => ({ sku: "REFRESH", images: [{ id: 1 }] }),
    downloadProductImages: async () => {
      imageDownloads += 1;
      return { downloaded: 1, attempted: 1 };
    },
    claimNextSourceRefreshJob: async () => {
      nextClaims += 1;
      return null;
    },
    failSourceRefreshJob: async () => ({}),
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));

  if (imageDownloads !== 0) throw new Error(`Expected price refresh to skip image downloads, got ${imageDownloads}`);
  if (!delays.includes(45 * 1000)) throw new Error(`Expected a 45 second cooldown, got ${JSON.stringify(delays)}`);
  if (nextClaims !== 0) throw new Error("Expected the next refresh job to wait for the cooldown.");
}

Promise.all([runContentTest(), runAutoImportTest(), runDelayedCaptureTest(), runSourceRefreshPacingTest()])
  .then(() => console.log("purchase-panel placement, auto-import, and delayed capture tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
