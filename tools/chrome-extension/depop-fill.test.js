const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

class Field {
  constructor(id, tagName = "INPUT") {
    this.id = id;
    this.tagName = tagName;
    this.value = "";
    this.events = [];
    this.style = {};
  }
  dispatchEvent(event) { this.events.push(event.type); }
  getBoundingClientRect() { return { width: 100, height: 30 }; }
  getAttribute() { return ""; }
}

async function run() {
  const saved = new Map();
  const fields = new Map([
    ["upload-input__input", new Field("upload-input__input")],
    ["description", new Field("description", "TEXTAREA")],
    ["priceAmount__input", new Field("priceAmount__input")],
  ]);
  let patch;
  const context = {
    URL,
    URLSearchParams,
    crypto: { randomUUID: () => "tab-7" },
    sessionStorage: {
      getItem: (key) => saved.get(key),
      setItem: (key, value) => saved.set(key, value),
      removeItem: (key) => saved.delete(key),
    },
    location: { search: "?autozs_fill=1&autozs_job_id=7&autozs_account_key=m4coq" },
    globalThis: {},
    setTimeout: (fn) => { fn(); return 1; },
    Event: class { constructor(type) { this.type = type; } },
    HTMLInputElement: class {},
    HTMLTextAreaElement: class {},
    document: {
      getElementById: (id) => fields.get(id) || null,
      querySelectorAll: (selector) => selector.includes("aria-label") ? [{href: "https://www.depop.com/m4coq/likes/"}] : [],
      addEventListener: () => {},
      createElement: () => new Field("badge", "DIV"),
      documentElement: { appendChild(element) { fields.set(element.id, element); } },
    },
    chrome: { storage: { local: {
      get: async () => ({}), set: async () => {}, remove: async () => {},
    } } },
    fetch: async (url, options = {}) => {
      if (url.endsWith("/depop/accounts")) return {ok:true, json:async()=> [{key:"m4coq",username:"m4coq",enabled:true,writes_enabled:true}]};
      if (options.method === "PATCH") {
        patch = JSON.parse(options.body);
        return { ok: true };
      }
      return {
        ok: true,
        json: async () => ({
          status: "running", account_key: "m4coq",
          title: "VOLGANIK ROCK purse - Red",
          description: "New statement purse.",
          price: 29.99,
          local_image_paths: [],
        }),
      };
    },
  };
  context.globalThis = context;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "depop-fill.js"), "utf8"), context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fields.get("description").value, "VOLGANIK ROCK purse - Red\n\nNew statement purse.");
  assert.equal(fields.get("priceAmount__input").value, "29.99");
  assert.equal(patch.status, "needs_review");
  assert.equal(patch.progress, 90);

  let confirmedPath = "";
  let removedPending = false;
  let recoveryNow = Date.now();
  const activeContext = {
    URL,
    URLSearchParams,
    location: {
      search: "",
      href: "https://www.depop.com/sellinghub/selling/active/",
      origin: "https://www.depop.com",
    },
    globalThis: {},
    setTimeout: (fn, ms) => { recoveryNow += ms; fn(); return 1; },
    Date: class extends Date { static now() { return recoveryNow; } },
    sessionStorage: context.sessionStorage,
    document: {
      getElementById: () => null,
      querySelectorAll: () => [{
        href: "https://www.depop.com/products/m4coq-red-purse-ab12/manage/",
        innerText: "US$41.60 Red vegan leather purse",
        closest: () => null,
      }],
      createElement: () => new Field("badge", "DIV"),
      documentElement: { appendChild() {} },
    },
    chrome: {
      storage: { local: {
        get: async () => ({ autozsDepopPendingPublication: {
          jobId: "7", tabToken: "tab-7", username: "m4coq", title: "Red purse", color: "Red", price: 41.6, postClickedAt: new Date().toISOString(),
        } }),
        remove: async () => { removedPending = true; },
        set: async () => {},
      } },
      runtime: { sendMessage: async (message) => {
        confirmedPath = message.path;
        return { ok: true, body: "{}" };
      } },
    },
  };
  activeContext.globalThis = activeContext;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "depop-fill.js"), "utf8"), activeContext);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(confirmedPath, "", "matching active card must not confirm a publication");
  assert.equal(removedPending, false);

  // Product navigation without exact product evidence stays uncertain.
  activeContext.document.querySelector = () => null;
  // The originating tab's immediate product redirect needs exact product evidence.
  activeContext.__AUTOZS_DEPOP_FILL__ = false;
  activeContext.location.href = "https://www.depop.com/products/m4coq-red-purse-ab12/";
  activeContext.document.referrer = "https://www.depop.com/products/create/?autozs_job_id=7";
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "depop-fill.js"), "utf8"), activeContext);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(confirmedPath, "");
  activeContext.__AUTOZS_DEPOP_FILL__ = false;
  activeContext.document.querySelectorAll = () => [{href:"https://www.depop.com/m4coq/likes/"}];
  activeContext.document.querySelector = () => ({querySelector: (selector) => selector.includes('name')
    ? {textContent: "Red purse"} : {getAttribute: () => "41.60"}});
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "depop-fill.js"), "utf8"), activeContext);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(confirmedPath, "/depop/jobs/7/published");
  assert.equal(removedPending, true);

  // A different tab has no originating token and cannot consume pending state.
  confirmedPath = "";
  removedPending = false;
  activeContext.__AUTOZS_DEPOP_FILL__ = false;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "depop-fill.js"), "utf8"), activeContext);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(confirmedPath, "");
  assert.equal(removedPending, false);

  // Reload/retry must retain an uncertain outcome rather than overwrite it.
  let overwrites = 0;
  context.__AUTOZS_DEPOP_FILL__ = false;
  context.chrome.storage.local.get = async () => ({ autozsDepopPendingPublication: {
    jobId: "7", postClickedAt: new Date().toISOString(),
  } });
  context.chrome.storage.local.set = async () => { overwrites++; };
  fields.get("description").value = "unchanged";
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "depop-fill.js"), "utf8"), context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(overwrites, 0);
  assert.equal(fields.get("description").value, "unchanged");
  assert.match(patch.message, /uncertain publication/);
  // An account mismatch stops before photos, field writes or pending state.
  context.__AUTOZS_DEPOP_FILL__ = false;
  context.chrome.storage.local.get = async () => ({});
  context.document.querySelectorAll = (selector) => selector.includes("aria-label")
    ? [{ href: "https://www.depop.com/someone-else/likes/" }] : [];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "depop-fill.js"), "utf8"), context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(overwrites, 0);
  assert.equal(fields.get("description").value, "unchanged");
  assert.match(patch.message, /signed-in username/);
  console.log("Depop fill tests passed.");
}

run();
