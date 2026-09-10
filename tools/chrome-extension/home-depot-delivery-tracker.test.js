const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/background.js`, 'utf8');
const context = { URL, Set };
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function homeDepotDeliveryTrackerNumber'), source.indexOf('async function reconcileSupplierTrackingObservation')), context);
const tracker = 'https://delivery-tracker.pr-sc-delivery-execution.gcp.homedepot.com/v1/orders/opaque/tracking/538849338995';
test('Home Depot dedicated tracker validates host and exact package number', () => {
  assert.equal(context.homeDepotDeliveryTrackerNumber(tracker), '538849338995');
  assert.equal(context.homeDepotDeliveryTrackerNumber(tracker.replace('https:', 'http:')), null);
  assert.equal(context.homeDepotDeliveryTrackerNumber(tracker.replace('.homedepot.com', '.example.com')), null);
  const text = 'Shipped Out For Delivery Delivered Tracking#: 538849338995 Shipment information sent to FedEx';
  const observation = context.homeDepotDeliveryTrackerObservation(text, '538849338995');
  assert.equal(observation.carrier, 'FedEx');
  assert.equal(observation.status, 'shipped');
  assert.equal(context.homeDepotDeliveryTrackerObservation(text, '999999999999'), null);
  assert.equal(context.homeDepotDeliveryTrackerObservation(text + ' UPS', '538849338995'), null);
  assert.equal(context.homeDepotDeliveryTrackerObservation('Shipped Out For Delivery Delivered Tracking#: 538849338995 FedEx', '538849338995'), null);
});
test('tracker capture uses verified supplier order identity and closes temporary tab', async () => {
  let captured;
  let closed;
  Object.assign(context, {
    setTimeout: resolve => resolve(),
    isHomeDepotTrackingUrl: (url, order) => order === 'WK37553521',
    recordSupplierTrackingResult: async () => {},
    reconcileSupplierTrackingObservation: async (url, observation) => { captured = observation; return { status: 'shipped' }; },
    chrome: { tabs: { create: async () => ({ id: 123 }), get: async () => ({ url: tracker }), remove: async id => { closed = id; } }, scripting: { executeScript: async () => [{ result: 'Tracking#: 538849338995 Shipment information sent to FedEx' }] } }
  });
  await context.captureHomeDepotDeliveryTracker({ url: 'https://www.homedepot.com/myaccount/order-details?orderNumber=WK37553521' }, tracker);
  assert.equal(captured.externalOrderId, 'WK37553521');
  assert.equal(captured.trackingNumber, '538849338995');
  assert.equal(closed, 123);
  captured = null;
  await assert.rejects(context.captureHomeDepotDeliveryTracker({ url: 'https://www.homedepot.com/myaccount/order-details?orderNumber=WRONG' }, tracker));
  assert.equal(captured, null);
});
