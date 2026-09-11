const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = { URL };
vm.createContext(context);
vm.runInContext(fs.readFileSync(`${__dirname}/home-depot-cart-quotes.js`, 'utf8'), context);
function doc(text, count = 1, quantity = '1', href = 'https://www.homedepot.com/p/Anvil/123456789') {
  return { body: { innerText: text }, querySelectorAll: () => Array.from({ length: count }, () => ({
    querySelectorAll: selector => selector.startsWith('a[') ? [{ href }] : [{ value: quantity }],
  })) };
}
const read = (text, ...args) => context.autozsReadDeliveryQuote(doc(text, ...args));
const paid = 'Delivering to 33101\nYour Order\nDelivery $35.00\nTotal $69.97';
assert.equal(read(paid).delivery_charge, 35);
assert.equal(read(paid).postal_code, '33101');
assert.equal(read(paid.replace('$35.00', 'FREE')).delivery_charge, 0);
for (const text of [paid.replace('33101', 'unknown'), paid + '\nDelivering to 10001',
  paid + '\nDelivery FREE', paid + '\nPickup FREE', paid + '\nUpdating',
  paid.replace('Your Order', 'Product details'), paid.replace('$35.00', 'TBD')]) {
  assert.equal(read(text), null, text);
}
assert.equal(read(paid, 2), null);
assert.equal(read(paid, 0), null);
assert.equal(read(paid, 1, ''), null);
assert.equal(read(paid, 1, '1', 'https://example.com/p/Anvil/123456789'), null);
console.log('Cart quote parser: paid/free and ambiguous evidence checks passed');
