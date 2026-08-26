const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/ebay-tracking-upload.js`, "utf8");
const context = {
  console,
  URL,
  window: null,
  document: { readyState: "loading", addEventListener() {} },
  globalThis: {},
};
context.window = context;
context.window.top = context.window;
vm.createContext(context);
vm.runInContext(source, context);
const helpers = context.globalThis.autozsEbayTrackingUploadTest;
const identity = helpers.trackingRunnerIdentity("https://www.ebay.com/sh/ord?q=03-15078-33225&autozs_workflow=tracking_upload&autozs_supplier_order_id=2");
if (!identity || identity.ebayOrderId !== "03-15078-33225" || identity.supplierOrderId !== 2) {
  throw new Error("Expected an exact marked eBay tracking runner identity.");
}
if (!helpers.trackingPayloadIsSafe({
  supplier_order_id: 2,
  ebay_order_id: "03-15078-33225",
  carrier: "UPS",
  tracking_number: "1Z999AA10123456784",
}, identity)) throw new Error("Expected an exact eBay tracking handoff to pass.");
if (helpers.trackingPayloadIsSafe({
  supplier_order_id: 3,
  ebay_order_id: "03-15078-33225",
  carrier: "UPS",
  tracking_number: "1Z999AA10123456784",
}, identity)) throw new Error("Expected a mismatched supplier order to fail closed.");
const confirmed = helpers.trackingSubmissionConfirmed(
  "Order 03-15078-33225 Tracking was successfully added: 1Z999AA10123456784",
  { ebay_order_id: "03-15078-33225", tracking_number: "1Z999AA10123456784" }
);
if (!confirmed) throw new Error("Expected an exact eBay tracking success confirmation.");
if (helpers.trackingSubmissionConfirmed(
  "Order 03-15078-33225 Tracking was successfully added: WRONG12345",
  { ebay_order_id: "03-15078-33225", tracking_number: "1Z999AA10123456784" }
)) throw new Error("Expected a mismatched eBay tracking confirmation to fail closed.");
if (/save[^\n]{0,120}\.click\(/i.test(source)) {
  throw new Error("The first eBay tracking canary must never click Save and Continue.");
}
if (!source.includes('type: "autozs-ebay-tracking-prepared"')) {
  throw new Error("Expected exact field read-back to report a prepared-state fingerprint.");
}
if (!source.includes('type: "autozs-ebay-tracking-submitted"')) {
  throw new Error("Expected eBay submission confirmation to trigger authoritative reconciliation.");
}
console.log("guarded eBay tracking preparation tests ok");
