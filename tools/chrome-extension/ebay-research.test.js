const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadResearchHelpers() {
  const source = fs.readFileSync(path.join(__dirname, "ebay-research.js"), "utf8");
  const window = {};
  const document = {
    readyState: "loading",
    addEventListener() {},
  };
  const context = {
    window,
    document,
    location: { pathname: "/sch/i.html", href: "https://www.ebay.com/sch/i.html" },
    URLSearchParams,
  };
  vm.createContext(context);
  vm.runInContext(source, context, { filename: "ebay-research.js" });
  return window.__autozsResearchTest;
}

test("eBay research helpers normalize sellers and score visible sales signals", () => {
  const helpers = loadResearchHelpers();

  assert.equal(helpers.normalizeSellerUsername("@Tweed&Till (22743)"), "Tweed&Till");
  assert.equal(helpers.normalizeSellerUsername("Save Seller"), "");
  assert.equal(helpers.sellerFromHref("https://www.ebay.com/usr/shlomisolomon"), "shlomisolomon");
  assert.equal(helpers.sellerFromHref("https://www.ebay.com/str/tweedtill"), "tweedtill");
  assert.equal(helpers.parseSoldCount("7 available - 5 sold"), 5);
  assert.equal(helpers.scoreListingText("25 sold in the last 24 hours"), 25025);
  assert.equal(helpers.searchResultSellerUsername("shlomisolomon ", "99.3% positive (791)"), "shlomisolomon");
  assert.equal(helpers.searchResultSellerUsername("tools-plus", "100% positive (673)"), "tools-plus");
  assert.equal(helpers.searchResultSellerUsername("Free delivery", "Located in United States"), "");
});
