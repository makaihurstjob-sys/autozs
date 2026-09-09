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
  const fields = new Map([
    ["upload-input__input", new Field("upload-input__input")],
    ["description", new Field("description", "TEXTAREA")],
    ["priceAmount__input", new Field("priceAmount__input")],
  ]);
  let patch;
  const context = {
    URLSearchParams,
    location: { search: "?autozs_fill=1&autozs_job_id=7" },
    globalThis: {},
    setTimeout: (fn) => { fn(); return 1; },
    Event: class { constructor(type) { this.type = type; } },
    HTMLInputElement: class {},
    HTMLTextAreaElement: class {},
    document: {
      getElementById: (id) => fields.get(id) || null,
      querySelectorAll: () => [],
      addEventListener: () => {},
      createElement: () => new Field("badge", "DIV"),
      documentElement: { appendChild(element) { fields.set(element.id, element); } },
    },
    fetch: async (url, options = {}) => {
      if (options.method === "PATCH") {
        patch = JSON.parse(options.body);
        return { ok: true };
      }
      return {
        ok: true,
        json: async () => ({
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
  const activeContext = {
    URL,
    URLSearchParams,
    location: {
      search: "",
      href: "https://www.depop.com/sellinghub/selling/active/",
      origin: "https://www.depop.com",
    },
    globalThis: {},
    setTimeout: (fn) => { fn(); return 1; },
    Date,
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
          jobId: "7", color: "Red", price: 41.6, postClickedAt: "2026-08-27T12:00:00Z",
        } }),
        remove: async () => { removedPending = true; },
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
  assert.equal(confirmedPath, "/depop/jobs/7/published");
  assert.equal(removedPending, true);
  console.log("Depop fill tests passed.");
}

run();
