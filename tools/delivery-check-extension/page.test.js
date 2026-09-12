const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(`${__dirname}/page.js`, 'utf8');

// Minimal in-memory DOM; no network, browser, API, or database access.
function harness({ labels = ['Log In', 'Delivery', 'Delivery Details', 'Add to Cart'], quantityCount = 1,
  body = '', title = '', cart = false } = {}) {
  const clicks = [];
  const controls = labels.map(value => ({
    innerText: value, disabled: false, getAttribute: () => null,
    getClientRects: () => [1], click: () => clicks.push(value),
  }));
  class Input {
    constructor() { this.current = '2'; }
    get value() { return this.current; }
    set value(value) { this.current = value; }
    getClientRects() { return [1]; }
    dispatchEvent() {}
  }
  const quantities = Array.from({ length: quantityCount }, () => new Input());
  const url = cart ? 'https://www.homedepot.com/mycart/home' : 'https://www.homedepot.com/p/Anvil/123456789';
  const document = {
    body: { innerText: body }, title,
    querySelector: () => ({ textContent: '0' }),
    querySelectorAll: selector => {
      if (selector === 'button, [role="button"], a') return controls;
      if (selector.includes('input[name*="quantity"')) return quantities;
      return [];
    },
  };
  const context = { document, location: new URL(url), URL, HTMLInputElement: Input, Event: class {} };
  vm.createContext(context); vm.runInContext(source, context);
  return { clicks, quantities, run: action => context.autozsDeliveryPage(action, { source_url: url, postal_code: '84532' }) };
}

for (const guestLabel of ['Log In', 'Sign In', 'Log In to your account', 'Sign In to your account']) {
  test(`${guestLabel} guest control permits inspecting empty cart`, () => {
    const h = harness({ labels: [guestLabel], cart: true, body: 'Your cart is empty' });
    assert.equal(h.run('inspect').empty, true);
    assert.deepEqual(h.clicks, []);
  });
}

test('exact Delivery wins over delivery details and ZIP controls', () => {
  const h = harness({ labels: ['Log In', 'Delivery', 'Delivery Details', 'Delivery to 84532', 'Add to Cart'] });
  assert.equal(h.run('prepare_product').prepared, true);
  assert.deepEqual(h.clicks, ['Delivery']);
  assert.equal(h.quantities[0].value, '1');
});

for (const deliveryLabels of [['Delivery', 'Delivery'], ['Delivery Details', 'Delivery to 84532']]) {
  test(`ambiguous or absent exact Delivery blocks mutation: ${deliveryLabels}`, () => {
    const h = harness({ labels: ['Log In', ...deliveryLabels] });
    assert.throws(() => h.run('prepare_product'), /missing or ambiguous/);
    assert.deepEqual(h.clicks, []);
  });
}

test('ambiguous quantity blocks preparation before clicking Delivery', () => {
  const h = harness({ quantityCount: 2 });
  assert.throws(() => h.run('prepare_product'), /quantity is ambiguous/);
  assert.deepEqual(h.clicks, []);
});

test('signed-in or unknown session cannot prepare product', () => {
  const h = harness({ labels: ['Hello Customer', 'Delivery', 'Add to Cart'] });
  assert.throws(() => h.run('prepare_product'), /guest session could not be verified/);
  assert.deepEqual(h.clicks, []);
});

test('page refresh request remains a transient error before guest detection', () => {
  const h = harness({ labels: [], body: 'Oops! Something went wrong. Please refresh page.' });
  assert.throws(() => h.run('inspect'), /Transient supplier page error/);
  assert.deepEqual(h.clicks, []);
});
