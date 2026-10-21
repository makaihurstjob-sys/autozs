const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(`${__dirname}/background.js`, 'utf8');

function harness(options = {}) {
  let now = 100000, empty = true, complete = false, addCount = 0, nextTabId = 7;
  const storage = {}, calls = [], actions = [];
  const tabs = options.existingTab ? [{ id: 99, url: 'https://www.homedepot.com/p/Other/1', status: 'complete' }] : [];
  const job = { id: 1, lease_token: 'x'.repeat(32), source_url: 'https://www.homedepot.com/p/Anvil/123456789', postal_code: '33101' };
  let context = {
    Date: { now: () => now }, crypto: { randomUUID: () => 'worker-id' }, setTimeout: () => {},
    fetch: async (url, request) => {
      const body = JSON.parse(request.body); calls.push({ url, body });
      if (options.networkDown) throw Error('network');
      if (url.endsWith('/claim')) return { ok: true, json: async () => job };
      if (url.endsWith('/heartbeat')) return { ok: !options.leaseInvalid, status: 409, json: async () => ({ status: complete ? 'completed' : 'running' }) };
      if (url.endsWith('/complete')) {
        complete = true;
        if (options.loseCompleteResponse) throw Error('connection lost');
        return { ok: true, json: async () => ({ status: 'completed' }) };
      }
      if (url.endsWith('/failed') && options.loseFailureResponse) throw Error('connection lost');
      return { ok: true, json: async () => ({ status: 'needs_review' }) };
    },
    autozsDeliveryPage: action => {
      if (options.supplierError) throw Error('Transient supplier page error: Home Depot requested a refresh');
      if (options.pageError) throw Error(options.pageError);
      if (action === 'inspect' && addCount && options.landOnInspect && --options.landOnInspect === 0) empty = false;
      if (action === 'inspect') return options.missingInspect ? undefined : {
        empty: options.foreignCart ? false : empty,
        cartMatches: !empty,
        quote: empty ? null : { source_url: job.source_url, postal_code: job.postal_code, quantity: 1, delivery_charge: 35 },
      };
      if (action === 'add') { addCount++; empty = !!options.addRefused; }
      if (action === 'remove' && !options.removeIgnored) empty = true;
      if (options.missingAction === action) return undefined;
      if (options.errorAfterAction === action) throw Error('Transient supplier page error: uncertain mutation');
      return { [{ prepare_product: 'prepared', add: 'added', zip: 'changed', remove: 'removed' }[action]]: true };
    },
    chrome: {
      storage: { local: {
        get: async () => structuredClone(storage),
        set: async values => Object.assign(storage, structuredClone(values)),
      } },
      tabs: {
        query: async () => [...tabs],
        create: async ({ url }) => { const tab = { id: nextTabId++, url, status: 'complete' }; tabs.push(tab); return tab; },
        get: async id => { const tab = tabs.find(t => t.id === id); if (!tab) throw Error(`No tab with id: ${id}`); return tab; },
        update: async (id, values) => Object.assign(tabs.find(t => t.id === id), values),
        reload: async () => actions.push('reload'),
        remove: async id => { const index = tabs.findIndex(t => t.id === id); if (index >= 0) tabs.splice(index, 1); },
        onUpdated: { addListener() {} },
      },
      scripting: { executeScript: async request => {
        if (request.files) return [];
        const action = request.args[0]; actions.push(action);
        if (options.frameError) return [{ error: { message: options.frameError } }];
        if (options.missingFrame) return [];
        if (options.nullFrame) return [null];
        return [{ result: await request.func(...request.args) }];
      } },
      alarms: { create() {}, onAlarm: { addListener() {} } },
      runtime: { onStartup: { addListener() {} }, onInstalled: { addListener() {} } },
    },
  };
  vm.createContext(context); vm.runInContext(source, context);
  return { storage, calls, actions, options, context, tabs,
    tick: async () => { now += 10000; await context.deliveryTick(); },
    advance: ms => { now += ms; },
    get addCount() { return addCount; }, get complete() { return complete; },
    restart: () => { context = vm.createContext({ ...context }); vm.runInContext(source, context); },
  };
}

test('isolated flow captures paid quote and confirms cleanup before completing', async () => {
  const h = harness();
  for (let i = 0; i < 10 && !h.complete; i++) await h.tick();
  assert.equal(h.complete, true);
  assert.equal(h.addCount, 1);
  assert.equal(h.storage.deliveryCheckState, null);
  assert.deepEqual(h.actions.filter(a => a !== 'inspect'), ['prepare_product', 'add', 'remove']);
  const result = h.calls.find(c => c.url.endsWith('/complete')).body;
  assert.equal(result.quote.delivery_charge, 35);
  assert.equal(result.cart_cleared, true);
});

test('restart after uncertain Add to Cart inspects cart without another add', async () => {
  const h = harness();
  for (let i = 0; i < 4; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState.phase, 'add_pending');
  h.restart();
  for (let i = 0; i < 6 && !h.complete; i++) await h.tick();
  assert.equal(h.complete, true);
  assert.equal(h.addCount, 1);
});

test('unknown existing tab prevents claiming or modifying any cart', async () => {
  const h = harness({ existingTab: true }); await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true);
  assert.equal(h.calls.length, 0); assert.equal(h.actions.length, 0);
});

test('nonempty initial cart is preserved and marked for review', async () => {
  const h = harness({ foreignCart: true }); await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true);
  assert.equal(h.addCount, 0); assert.equal(h.actions.includes('remove'), false);
  assert.equal(h.calls.at(-1).body.retryable, false);
});

test('invalid lease stops before reading or mutating the page', async () => {
  const h = harness(); await h.tick(); h.options.leaseInvalid = true; await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true); assert.equal(h.actions.length, 0);
});

test('network outage preserves state and resumes after connectivity returns', async () => {
  const h = harness(); await h.tick(); h.options.networkDown = true; await h.tick();
  assert.equal(h.storage.deliveryCheckState.phase, 'initial');
  assert.equal(h.actions.length, 0);
  h.options.networkDown = false; await h.tick();
  assert.equal(h.storage.deliveryCheckState.phase, 'product');
});

test('lost completion response is recovered without duplicate cart work', async () => {
  const h = harness({ loseCompleteResponse: true });
  for (let i = 0; i < 10 && !h.complete; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState.phase, 'complete');
  await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.addCount, 1);
  assert.equal(h.calls.filter(c => c.url.endsWith('/complete')).length, 1);
});

test('supplier refresh errors before adding back off without pausing the worker', async () => {
  const h = harness({ supplierError: true });
  for (let i = 0; i < 5; i++) await h.tick();
  assert.equal(h.actions.filter(a => a === 'reload').length, 3);
  assert.equal(h.addCount, 0);
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.tabs.length, 0);
  assert.equal(h.calls.at(-1).body.retryable, true);
});

test('unrendered delivery tile re-checks, then backs off without pausing the worker', async () => {
  const h = harness();
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState.phase, 'product');
  h.options.pageError = 'Delivery control is missing or ambiguous';
  for (let i = 0; i < 4; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState.phase, 'product');
  assert.equal(h.actions.filter(a => a === 'reload').length, 1);
  assert.equal(h.calls.some(c => c.url.endsWith('/failed')), false);
  await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.tabs.length, 0);
  assert.equal(h.addCount, 0);
  assert.equal(h.calls.at(-1).body.retryable, true);
});

test('delivery tile that renders late completes the same job', async () => {
  const h = harness();
  await h.tick(); await h.tick();
  h.options.pageError = 'Delivery control is missing or ambiguous';
  await h.tick(); await h.tick();
  h.options.pageError = null;
  for (let i = 0; i < 10 && !h.complete; i++) await h.tick();
  assert.equal(h.complete, true);
  assert.equal(h.addCount, 1);
});

test('refused add confirmed empty twice backs off without pausing the worker', async () => {
  const h = harness({ addRefused: true });
  for (let i = 0; i < 10 && h.storage.deliveryCheckState !== null; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.tabs.length, 0);
  assert.equal(h.addCount, 1);
  assert.equal(h.actions.filter(a => a === 'reload').length, 1);
  const failure = h.calls.find(c => c.url.endsWith('/failed')).body;
  assert.equal(failure.retryable, true);
  assert.match(failure.message, /cart confirmed empty twice/);
});

test('cart that shows the item after a reload completes without another add', async () => {
  const h = harness({ addRefused: true, landOnInspect: 2 });
  for (let i = 0; i < 12 && !h.complete; i++) await h.tick();
  assert.equal(h.complete, true);
  assert.equal(h.addCount, 1);
  assert.equal(h.calls.some(c => c.url.endsWith('/failed')), false);
});

test('supplier error after a possible add preserves the cart for review', async () => {
  const h = harness();
  for (let i = 0; i < 4; i++) await h.tick();
  h.options.supplierError = true;
  for (let i = 0; i < 10; i++) await h.tick();
  assert.equal(h.actions.filter(a => a === 'reload').length, 8);
  assert.equal(h.addCount, 1);
  assert.equal(h.storage.deliveryCheckState.paused, true);
  assert.equal(h.tabs.length, 1);
  assert.equal(h.calls.at(-1).body.retryable, false);
  assert.equal(h.actions.includes('remove'), false);
});

test('cart page errors after a refused add recover once the cart loads empty', async () => {
  const h = harness({ addRefused: true });
  for (let i = 0; i < 5; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState.phase, 'cart');
  h.options.supplierError = true;
  for (let i = 0; i < 5; i++) await h.tick();
  assert.notEqual(h.storage.deliveryCheckState.paused, true);
  h.options.supplierError = false;
  for (let i = 0; i < 6 && h.storage.deliveryCheckState !== null; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.addCount, 1);
  assert.equal(h.calls.at(-1).body.retryable, true);
});

test('uncertain failure report preserves state instead of claiming another job', async () => {
  const h = harness({ supplierError: true, loseFailureResponse: true });
  for (let i = 0; i < 6; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true);
  assert.equal(h.tabs.length, 1);
  assert.equal(h.addCount, 0);
  assert.equal(h.calls.filter(c => c.url.endsWith('/claim')).length, 1);
});


test('guest header that hydrates late completes the same job', async () => {
  const h = harness();
  await h.tick(); await h.tick();
  h.options.pageError = 'Signed-out guest session could not be verified';
  await h.tick(); await h.tick();
  assert.equal(h.calls.some(c => c.url.endsWith('/failed')), false);
  h.options.pageError = null;
  for (let i = 0; i < 10 && !h.complete; i++) await h.tick();
  assert.equal(h.complete, true);
  assert.equal(h.addCount, 1);
});

test('injected page exceptions retain the actual failure reason', async () => {
  const h = harness({ pageError: 'Browser verification requires review' });
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState.message, h.options.pageError);
  assert.equal(h.calls.at(-1).body.message, h.options.pageError);
});

test('frame execution errors retain their failure reason', async () => {
  const h = harness({ frameError: 'Page script failed' });
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState.message, 'Page script failed');
});

for (const option of ['missingInspect', 'missingFrame', 'nullFrame']) {
  test(option + ' remains a hard evidence failure', async () => {
    const h = harness({ [option]: true });
    await h.tick(); await h.tick();
    assert.equal(h.storage.deliveryCheckState.message, 'Missing delivery page evidence');
    assert.equal(h.addCount, 0);
    assert.equal(h.complete, false);
  });
}

for (const action of ['prepare_product', 'add', 'remove']) {
  test('missing ' + action + ' acknowledgement never repeats the action', async () => {
    const h = harness({ missingAction: action });
    for (let i = 0; i < 12; i++) await h.tick();
    h.restart(); await h.tick();
    assert.equal(h.storage.deliveryCheckState.paused, true);
    assert.equal(h.actions.filter(a => a === action).length, 1);
    assert.equal(h.complete, false);
  });
}

for (const action of ['add', 'remove']) {
  test('transient error after ' + action + ' reconciles without replay', async () => {
    const h = harness({ errorAfterAction: action });
    for (let i = 0; i < 12 && !h.complete; i++) await h.tick();
    assert.equal(h.complete, true);
    assert.equal(h.actions.filter(a => a === action).length, 1);
    assert.equal(h.addCount, 1);
  });
}

const MINUTE = 60 * 1000;

test('unreviewed pause with an empty guest cart resumes the queue without cart changes', async () => {
  const h = harness({ pageError: 'Browser verification requires review' });
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true);
  h.options.pageError = null;
  const reads = h.actions.length;
  for (let i = 0; i < 3; i++) await h.tick();
  assert.equal(h.actions.length, reads);
  assert.equal(h.tabs.length, 1);
  h.advance(15 * MINUTE);
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.tabs.length, 0);
  assert.deepEqual(h.actions.slice(reads), ['inspect']);
  assert.equal(h.storage.deliveryRecoveryArchive.job.id, 1);
  assert.equal(h.storage.deliveryRecoveryArchive.recoveredBy, 'worker');
  assert.deepEqual(h.calls.filter(c => c.url.endsWith('/cart-cleared')).map(c => [c.url.split('/').at(-2), c.body]),
    [['1', { worker_id: 'delivery-worker-id' }]]);
  await h.tick();
  assert.equal(h.calls.filter(c => c.url.endsWith('/claim')).length, 2);
  assert.equal(h.storage.deliveryCheckState.phase, 'initial');
  assert.equal(h.addCount, 0);
});

test('pause saved before rechecks existed is read on the next tick', async () => {
  const h = harness();
  h.storage.deliveryCheckState = { paused: true, message: 'Signed-out guest session could not be verified', phase: 'product', tabId: 5,
    workerId: 'delivery-old', job: { id: 8, lease_token: 'y'.repeat(32), source_url: 'https://www.homedepot.com/p/Spinach/313508261', postal_code: '11706' } };
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.storage.deliveryRecoveryArchive.job.id, 8);
  assert.deepEqual(h.actions, ['inspect']);
  assert.deepEqual(h.calls.map(c => [c.url.split('/').slice(-2).join('/'), c.body]), [['8/cart-cleared', { worker_id: 'delivery-old' }]]);
});

test('unreachable API after a clean recovery still resumes the queue', async () => {
  const h = harness({ pageError: 'Browser verification requires review' });
  await h.tick(); await h.tick();
  h.options.pageError = null;
  h.options.networkDown = true;
  h.advance(15 * MINUTE);
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  h.options.networkDown = false;
  await h.tick();
  assert.equal(h.storage.deliveryCheckState.phase, 'initial');
});

test('pause holding only its own test item removes it once, then resumes', async () => {
  const h = harness();
  for (let i = 0; i < 4; i++) await h.tick();
  h.options.supplierError = true;
  for (let i = 0; i < 10; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true);
  h.options.supplierError = false;
  h.advance(15 * MINUTE);
  for (let i = 0; i < 3 && h.storage.deliveryCheckState !== null; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.actions.filter(a => a === 'remove').length, 1);
  assert.equal(h.addCount, 1);
  assert.equal(h.tabs.length, 0);
  assert.ok(h.storage.deliveryRecoveryArchive.recoveryRemovedAt);
  assert.equal(h.calls.filter(c => c.url.endsWith('/jobs/1/cart-cleared')).length, 1);
});

test('recovery never repeats a removal that did not land', async () => {
  const h = harness({ removeIgnored: true });
  for (let i = 0; i < 4; i++) await h.tick();
  h.options.supplierError = true;
  for (let i = 0; i < 10; i++) await h.tick();
  h.options.supplierError = false;
  h.advance(15 * MINUTE);
  for (let i = 0; i < 3; i++) await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true);
  assert.equal(h.storage.deliveryCheckState.recoveryMessage, 'Test-item removal was not confirmed');
  h.advance(30 * MINUTE);
  for (let i = 0; i < 3; i++) await h.tick();
  assert.equal(h.actions.filter(a => a === 'remove').length, 1);
  assert.equal(h.storage.deliveryCheckState.paused, true);
  assert.equal(h.storage.deliveryCheckState.recoveryAttempts, 2);
  assert.equal(h.addCount, 1);
});

test('cart contents this worker did not add stay paused and are rechecked with backoff', async () => {
  const h = harness({ foreignCart: true });
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true);
  h.advance(15 * MINUTE);
  await h.tick(); await h.tick();
  const state = h.storage.deliveryCheckState;
  assert.equal(state.paused, true);
  assert.equal(state.recovery, undefined);
  assert.equal(state.recoveryAttempts, 1);
  assert.equal(state.recoveryMessage, 'Guest cart holds items this worker did not add');
  assert.equal(h.tabs.length, 1);
  assert.equal(h.actions.includes('remove'), false);
  const reads = h.actions.length;
  h.advance(15 * MINUTE); await h.tick();
  assert.equal(h.tabs.length, 1);
  h.advance(15 * MINUTE); await h.tick(); await h.tick();
  assert.equal(h.actions.length, reads + 1);
  assert.equal(h.storage.deliveryCheckState.recoveryAttempts, 2);
});

test('a recovery read that is still blocked keeps the pause', async () => {
  const h = harness({ pageError: 'Browser verification requires review' });
  await h.tick(); await h.tick();
  h.advance(15 * MINUTE);
  await h.tick(); await h.tick();
  const state = h.storage.deliveryCheckState;
  assert.equal(state.paused, true);
  assert.equal(state.message, 'Browser verification requires review');
  assert.equal(state.recoveryMessage, 'Browser verification requires review');
  assert.equal(h.tabs.length, 1);
});

test('leftover supplier tab is closed only after an unreviewed pause reads an empty cart', async () => {
  const h = harness({ existingTab: true });
  await h.tick();
  assert.equal(h.storage.deliveryCheckState.paused, true);
  await h.tick();
  assert.equal(h.tabs.length, 1);
  h.advance(15 * MINUTE);
  await h.tick(); await h.tick();
  assert.equal(h.storage.deliveryCheckState, null);
  assert.equal(h.tabs.length, 0);
  assert.equal(h.calls.length, 0);
  await h.tick();
  assert.equal(h.calls.filter(c => c.url.endsWith('/claim')).length, 1);
});
