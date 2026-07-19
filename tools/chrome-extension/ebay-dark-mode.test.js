const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(`${__dirname}/ebay-dark-mode.js`, "utf8");
const elements = new Map();
const rootClasses = new Set();
const classList = {
  contains: (name) => rootClasses.has(name),
  toggle: (name, enabled) => enabled ? rootClasses.add(name) : rootClasses.delete(name),
};
const head = {
  appendChild(element) {
    elements.set(element.id, element);
  },
};
const document = {
  body: {},
  documentElement: { classList },
  head,
  addEventListener() {},
  createElement() {
    return {
      attributes: new Map(),
      id: "",
      textContent: "",
      getAttribute(name) { return this.attributes.get(name) || ""; },
      setAttribute(name, value) { this.attributes.set(name, String(value)); },
    };
  },
  getElementById: (id) => elements.get(id) || null,
  querySelectorAll: () => [],
};
const matchMedia = () => ({ matches: true, addEventListener() {} });
const context = {
  console,
  document,
  fetch: async () => ({ ok: true, json: async () => ({ ui_theme: "dark" }) }),
  location: { pathname: "/sl/prelist/identify" },
  matchMedia,
  MutationObserver: class { observe() {} },
  setTimeout() {},
  window: {
    addEventListener() {},
    matchMedia,
  },
};
context.window.window = context.window;

vm.createContext(context);
vm.runInContext(source, context, { filename: "ebay-dark-mode.js" });

setImmediate(() => {
  const style = elements.get("autozs-ebay-dark-mode-style");
  assert.ok(rootClasses.has("autozs-ebay-dark-mode"), "Expected dark mode to be enabled.");
  assert.ok(rootClasses.has("autozs-ebay-listing-editor"), "Expected listing-editor contrast scope on /sl/prelist.");
  assert.ok(rootClasses.has("autozs-ebay-prelist"), "Expected dedicated pre-list contrast scope.");
  assert.match(style.textContent, /autozs-ebay-listing-editor \.listbox-button__control/);
  assert.match(style.textContent, /autozs-ebay-listing-editor \.summary-container/);
  assert.match(style.textContent, /autozs-ebay-listing-editor \.summary__attributes--label/);
  assert.match(style.textContent, /autozs-ebay-listing-editor \.summary__legal-faq/);
  assert.match(style.textContent, /autozs-ebay-listing-editor \.listbox__options/);
  assert.match(style.textContent, /autozs-ebay-listing-editor \.dp-container/);
  assert.match(style.textContent, /autozs-ebay-listing-editor \.date-picker \.day\.selected/);
  assert.match(style.textContent, /autozs-ebay-listing-editor \.btn--primary/);
  assert.match(style.textContent, /autozs-ebay-prelist \[role="contentinfo"\]/);
  assert.match(style.textContent, /autozs-ebay-prelist button\[disabled\]/);
  assert.match(style.textContent, /autozs-ebay-prelist button\.fake-link/);
  assert.match(style.textContent, /#gh-eb-My-o/);
  assert.match(style.textContent, /data-menu-name="my-ebay"/);
  assert.match(style.textContent, /aria-label\*="My eBay" i/);
  assert.match(style.textContent, /#gh \[class\*="myebay" i\] a:hover/);
  console.log("eBay listing editor and pre-list dark-mode contrast tests ok");
});
