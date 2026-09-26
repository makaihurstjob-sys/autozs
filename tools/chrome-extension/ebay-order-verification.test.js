const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/ebay-order-verification.js`, 'utf8');
const identity = { supplier_order_id: 9, ebay_order_id: '02-15229-83590', account_key: 'a.m.anim-59' };
const prefix = 'Seller Hub a.m.anim-59 View profile Order details Nozzle ';
const suffix = ' Shipping instructions Ship on time If shipping without tracking mark the order as shipped Ship to buyer Tracking -- Add tracking Item Nozzle Add tracking Order Order 02-15229-83590 Buyer paid Sep 25';
const snapshot = (header = 'Ship by Sep 30 Buyer paid Sep 25 Ship by Sep 30 Delivery Shipping') => ({
  url: 'https://www.ebay.com/mesh/ord/details?mode=SH&orderid=02-15229-83590', readyState: 'complete', text: prefix + header + suffix,
});
const context = { URL, LOCAL_CHECKOUT_API: "http://127.0.0.1:8000", setTimeout: fn => fn() };
vm.createContext(context);
vm.runInContext(source, context);
const classify = s => context.classifyEbayOrderSnapshot(s, identity).status;
assert.equal(classify(snapshot()), 'eligible'); // Generic shipping advice isn't a shipped status.
for (const header of ['This order was canceled Refund initiated Sep 20', 'Cancellation requested Buyer paid Sep 25']) assert.equal(classify(snapshot(header)), 'cancelled');
assert.equal(classify(snapshot('Refund initiated Sep 22')), 'refunded');
for (const header of ['Shipped Label created Sep 26', 'Delivered Sep 28', 'In transit']) assert.equal(classify(snapshot(header)), 'fulfilled');
for (const patch of [
  { readyState: 'loading' }, { url: 'https://www.ebay.com/sh/ord?q=02-15229-83590' },
  { url: 'https://www.ebay.com/mesh/ord/details?orderid=22-15176-66586' },
  { text: snapshot().text.replace('a.m.anim-59', 'other-account') },
  { text: snapshot().text.replace('Order Order 02-15229-83590', 'Order Order 22-15176-66586') },
  { text: 'imported sync completed Buyer paid Sep 25 Ship by Sep 30' },
]) assert.equal(classify({ ...snapshot(), ...patch }), 'unknown');
assert.equal(classify(snapshot('Awaiting payment Ship by Sep 30')), 'unknown');
assert.equal(classify({ ...snapshot(), text: snapshot().text.replace('Tracking --', 'Tracking 383834604886') }), 'fulfilled');
assert.equal(classify({ ...snapshot(), text: snapshot().text + ' Refund pending' }), 'refunded');
assert.equal(classify({ ...snapshot(), text: snapshot().text + ' Cancellation pending' }), 'cancelled');

async function run() {
  const events = [];
  let page = snapshot();
  context.chrome = {
    tabs: { create: async () => ({ id: 100 }), remove: async id => events.push(['closed', id]) },
    scripting: { executeScript: async () => [{ result: page }] },
  };
  context.fetch = async (path, options) => { events.push(['record', path, JSON.parse(options.body)]); return { ok: true }; };
  await context.verifyLiveEbaySupplierOrder(identity);
  assert.equal(events[0][2].status, 'eligible');
  assert.equal(events[0][2].account_key, identity.account_key);
  assert.equal(events[1][0], 'closed');
  events.length = 0;
  page = snapshot('This order was canceled');
  await assert.rejects(() => context.verifyLiveEbaySupplierOrder(identity), /cancelled/);
  assert.equal(events[0][2].status, 'cancelled');
  assert.equal(events[1][0], 'closed');
  page = { ...snapshot(), readyState: 'loading' };
  await assert.rejects(() => context.verifyLiveEbaySupplierOrder(identity), /unknown/);
  page = snapshot();
  context.fetch = async () => ({ ok: false, status: 503 });
  await assert.rejects(() => context.verifyLiveEbaySupplierOrder(identity), /persistence failed/);
  assert.equal(events.at(-1)[0], 'closed');
  console.log('Live eBay verifier: identity, status, fail-closed and broker tests passed.');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
