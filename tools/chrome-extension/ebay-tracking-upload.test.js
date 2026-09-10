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
if (!source.includes('type: "autozs-ebay-tracking-prepared"')) {
  throw new Error("Expected exact field read-back to report a prepared-state fingerprint.");
}
if (!source.includes('type: "autozs-ebay-tracking-submitted"')) {
  throw new Error("Expected eBay submission confirmation to trigger authoritative reconciliation.");
}
console.log("guarded eBay tracking preparation tests ok");
const assert = require('node:assert/strict');
const test = require('node:test');
test('automatic submission is once-only and refuses a mismatched order', async () => {
  let clicks = 0;
  const saved = {};
  const candidate = { supplier_order_id: 2, ebay_order_id: '03-15078-33225', carrier: 'UPS', tracking_number: '1Z999AA10123456784' };
  const input = () => ({value:'',getBoundingClientRect:()=>({width:10,height:10}),dispatchEvent(){},focus(){},blur(){}});
  const inputs = [input(), input()];
  const save = {textContent:'Save and Continue',disabled:false,getAttribute:()=>null,click(){clicks++;}};
  context.location = {href:'https://www.ebay.com/ship/trk/trackings',pathname:'/ship/trk/trackings',assign(url){this.redirect=url;}};
  context.history = {replaceState(){}};
  context.HTMLInputElement = function(){};
  context.InputEvent = context.Event = function(){};
  context.setTimeout = resolve => { if (resolve.toString().includes('observer.disconnect')) return; resolve(); };
  context.MutationObserver = class { observe(){} disconnect(){} };
  context.sessionStorage = {setItem(k,v){saved[k]=v;},removeItem(k){delete saved[k];}};
  context.chrome = {runtime:{sendMessage(_m,cb){cb({ok:true});}}};
  context.document.body = {innerText:'Order '+candidate.ebay_order_id};
  context.document.querySelectorAll = selector => selector==='input[type="text"]'?inputs:selector==='button'?[save]:[];
  context.document.getElementById = () => ({style:{},textContent:''});
  await helpers.fillTrackingForm(candidate);
  assert.equal(clicks,1);
  assert.equal(JSON.parse(saved.autozs_ebay_tracking_upload).submission_attempted,true);
  await helpers.fillTrackingForm(candidate);
  assert.equal(clicks,1);
  assert.ok(context.location.redirect.includes(candidate.ebay_order_id));
  context.document.body.innerText='A different order';
  await assert.rejects(helpers.fillTrackingForm({...candidate,submission_attempted:false}),/exact eBay order ID/);
  assert.equal(clicks,1);
  assert.equal(helpers.trackingRecordPresent('Order 03-15078-33225 Shipped UPS Tracking 1Z999AA10123456784',candidate),true);
  assert.equal(helpers.trackingRecordPresent('Order 03-15078-33225 Shipped FedEx Tracking 1Z999AA10123456784',candidate),false);
});
require('node:test')('tracking script initializes inside the eBay tracking iframe only', () => {
  const assert = require('node:assert/strict');
  const frame = { console, URL, window: { top: {} }, location: { hostname: 'www.ebay.com', pathname: '/ship/trk/trackings' }, document: { readyState: 'loading', addEventListener() {} }, globalThis: {} };
  vm.createContext(frame);
  vm.runInContext(source, frame);
  assert.equal(typeof frame.globalThis.autozsEbayTrackingUploadTest.fillTrackingForm, 'function');
  frame.location.pathname = '/unrelated';
  frame.globalThis = {};
  vm.runInContext(source, frame);
  assert.equal(frame.globalThis.autozsEbayTrackingUploadTest, undefined);
});
require('node:test')('saved tracking must belong to the exact order row', () => {
  const assert = require('node:assert/strict');
  const candidate = { ebay_order_id: '08-15143-56000', tracking_number: '538849338995' };
  context.document.querySelectorAll = () => [{ textContent: '538849338995', closest: () => ({ textContent: 'Order 08-15143-56000 Tracking 538849338995' }) }];
  assert.equal(helpers.savedTrackingRowPresent(candidate), true);
  assert.equal(helpers.savedTrackingRowPresent({ ...candidate, ebay_order_id: '03-15078-33225' }), false);
  assert.equal(helpers.savedTrackingRowPresent({ ...candidate, tracking_number: '999999999999' }), false);
});
