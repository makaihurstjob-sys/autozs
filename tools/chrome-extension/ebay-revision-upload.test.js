const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/ebay-revision-upload.js`, "utf8");

class FakeElement {
  constructor({ text = "", tagName = "DIV", cells = [], visible = true, attrs = {} } = {}) {
    this.innerText = text;
    this.textContent = text;
    this.tagName = tagName;
    this.cells = cells;
    this.visible = visible;
    this.attrs = attrs;
    this.clicked = false;
  }

  click() {
    this.clicked = true;
  }

  getAttribute(key) {
    return this.attrs[key] || "";
  }

  querySelectorAll(selector) {
    if (selector === '[role="gridcell"], td, th') return this.cells;
    if (selector === 'a,button,[role="button"]') return this.downloads || [];
    return [];
  }

  getBoundingClientRect() {
    return this.visible ? { width: 120, height: 28 } : { width: 0, height: 0 };
  }

  get offsetWidth() {
    return this.visible ? 120 : 0;
  }

  get offsetHeight() {
    return this.visible ? 28 : 0;
  }

  getClientRects() {
    return this.visible ? [{ width: 120, height: 28 }] : [];
  }
}

async function runRenamedUploadResultTest() {
  const expectedFilename = "autozs-price-revisions-main-store-20260702153746.csv";
  const ebayRenamedFilename = "autozs-price-revisions-main-store-20260702153746-Jul-2026-02-08-37-48-13311709092.csv";
  const downloadMenuButton = new FakeElement({ text: "Download results", tagName: "BUTTON" });
  const downloadOutputLink = new FakeElement({
    text: "Download results",
    tagName: "A",
    visible: false,
    attrs: { href: "/sh/fpp/getfiledetails?client=fileexchange&requestId=123&filetype=output&fileName=result.csv" },
  });
  const row = new FakeElement({
    text: `${ebayRenamedFilename} Completed Download results`,
    cells: [
      new FakeElement({ text: ebayRenamedFilename }),
      new FakeElement({ text: "Completed" }),
      new FakeElement({ text: "Download results" }),
    ],
  });
  row.downloads = [downloadMenuButton, downloadOutputLink];

  const patches = [];
  let resultContextPrepared = 0;
  const context = {
    console,
    setTimeout,
    URLSearchParams,
    API: "http://127.0.0.1:8000",
    location: {
      search: "?autozs_revision_batch=7&autozs_account_key=main-store",
      pathname: "/sh/reports/uploads",
    },
    window: {},
    document: {
      querySelectorAll: (selector) => {
        if (selector === '[role="row"], tr') return [row];
        if (selector === "button") return [];
        if (selector === 'button, a, [role="button"], label') return [];
        return [];
      },
      querySelector: () => null,
    },
    chrome: {
      runtime: {
        sendMessage: async (message) => {
          if (message?.type === "autozs-ebay-revision-result-context" && message.batchId === 7) {
            resultContextPrepared += 1;
            return { ok: true };
          }
          return { ok: false, error: "unexpected message" };
        },
      },
    },
    reportEbayBrowserAccount: async () => ({ can_list: true }),
    fetch: async (url, options = {}) => {
      if (String(url).endsWith("/ebay/revision-batches/7") && !options.method) {
        return {
          ok: true,
          json: async () => ({
            id: 7,
            account_key: "main-store",
            filename: expectedFilename,
            status: "waiting_results",
          }),
        };
      }
      if (String(url).endsWith("/ebay/revision-batches/7") && options.method === "PATCH") {
        patches.push(JSON.parse(options.body || "{}"));
        return {
          ok: true,
          json: async () => ({ id: 7, ...patches[patches.length - 1] }),
        };
      }
      throw new Error(`Unexpected fetch ${url}`);
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));

  if (!downloadOutputLink.clicked || downloadMenuButton.clicked) {
    throw new Error("Expected AutoZS to click the output-file link instead of eBay's duplicate download menu button.");
  }
  if (resultContextPrepared !== 1) {
    throw new Error(`Expected one prepared result download context, got ${resultContextPrepared}`);
  }
  if (patches.some((patch) => patch.status === "needs_review")) {
    throw new Error(`Expected renamed upload result to avoid needs_review, got ${JSON.stringify(patches)}`);
  }
}

async function runNeedsReviewRetryTest() {
  const expectedFilename = "autozs-price-revisions-main-store-20260703040048.csv";
  const downloadOutputLink = new FakeElement({
    text: "Download results",
    tagName: "A",
    visible: false,
    attrs: { href: "/sh/fpp/getfiledetails?client=fileexchange&requestId=456&filetype=output&fileName=result.csv" },
  });
  const row = new FakeElement({
    text: `${expectedFilename}-renamed.csv Completed Download results`,
    cells: [
      new FakeElement({ text: expectedFilename }),
      new FakeElement({ text: "Completed" }),
      new FakeElement({ text: "Download results" }),
    ],
  });
  row.downloads = [downloadOutputLink];

  const context = {
    console,
    setTimeout,
    URLSearchParams,
    API: "http://127.0.0.1:8000",
    location: { search: "?autozs_revision_batch=5&autozs_account_key=main-store", pathname: "/sh/reports/uploads" },
    window: {},
    document: {
      querySelectorAll(selector) { return selector === '[role="row"], tr' ? [row] : []; },
      querySelector() { return null; },
    },
    chrome: { runtime: { async sendMessage() { return { ok: true }; } } },
    reportEbayBrowserAccount: async () => ({ can_list: true }),
    fetch: async (url) => {
      if (String(url).includes("/ebay/revision-batches/5")) {
        return { ok: true, async json() { return { id: 5, status: "needs_review", filename: expectedFilename }; } };
      }
      throw new Error(`Unexpected fetch: ${url}`);
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));
  if (!downloadOutputLink.clicked) throw new Error("Expected a needs-review retry to download the existing eBay result.");
}

runRenamedUploadResultTest()
  .then(runNeedsReviewRetryTest)
  .then(() => console.log("ebay revision upload tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
