const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

function run() {
  let listener;
  const context = {
    globalThis: {},
    document: {
      title: "Depop",
      body: { innerText: "Sell Saved Messages" },
      documentElement: { dataset: {} },
    },
    location: { href: "https://www.depop.com/selling/" },
    chrome: { runtime: { onMessage: { addListener(fn) { listener = fn; } } } },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "depop-profile.js"), "utf8"), context);
  let response;
  listener({ type: "autozs:depop-profile-status" }, {}, (value) => { response = value; });
  assert.equal(response.marketplace, "depop");
  assert.equal(response.signedIn, true);
  assert.equal(context.document.documentElement.dataset.autozsDepopProfile, "signed-in");
  console.log("Depop profile scaffold tests passed.");
}

run();
