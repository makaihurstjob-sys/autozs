const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

function run() {
  let listener;
  const context = {
    globalThis: {}, URL,
    document: {
      querySelectorAll:()=>[{href:"https://www.depop.com/m4coq/likes/"}],
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
  assert.equal(response.username, "m4coq");
  assert.equal(context.document.documentElement.dataset.autozsDepopProfile, "signed-in");
  context.location.href = "https://www.depop.com/login/";
  listener({ type: "autozs:depop-profile-status" }, {}, value => { response = value; });
  assert.equal(response.signedIn, false, 'login redirect overrides stale header');
  context.location.href = "https://www.depop.com/selling/";
  context.document.querySelectorAll = () => [];
  listener({ type: "autozs:depop-profile-status" }, {}, value => { response = value; });
  assert.equal(response.signedIn, false, 'loading or expired session cannot authorize');
  context.document.querySelectorAll = () => [{href:'https://www.depop.com/a/likes/'},{href:'https://www.depop.com/b/likes/'}];
  listener({ type: "autozs:depop-profile-status" }, {}, value => { response = value; });
  assert.equal(response.signedIn, false, 'ambiguous account held');
  console.log("Depop profile scaffold tests passed.");
}

run();
