const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/background.js`, 'utf8');
const worker = source.slice(source.indexOf('let profitReconciliationRunning'), source.indexOf('async function claimNextEbayOrderSync'));
async function run(fail = false) {
  const posts = [], removed = [];
  const context = {
    URL, setTimeout: fn => fn(), canRunAutozsWorkerJobs: async () => true,
    matchedEbayAccountKey: async () => 'internal-account-key',
    localApiJson: async (path, options) => {
      if (path.includes('browser-account')) return {can_list:true, expected_username:'seller-name'};
      if (path.includes('/next?')) return {order_id:1, ebay_order_id:'order-123', url:'https://www.ebay.com/mesh/ord/details?orderid=order-123'};
      posts.push(JSON.parse(options.body));
    },
    chrome: {tabs: {create: async () => ({id:42}), remove: async id => removed.push(id)},
      scripting: {executeScript: async ({func,args}) => {
        context.document = {body:{innerText: fail ? 'Sign in' : 'seller-name order-123 What your buyer paid Subtotal $9.53 Order earnings $7.74'}};
        context.location = {href:'https://www.ebay.com/mesh/ord/details?orderid=order-123'};
        context.args = args;
        return [{result: vm.runInContext(`(${func.toString()})(...args)`,context)}];
      }}}
  };
  vm.createContext(context);
  await vm.runInContext(worker + '\nreconcileNextOrderProfit()', context);
  assert.deepEqual(removed,[42]);
  assert.equal(posts.length,1);
  if (fail) assert.match(posts[0].error,/could not be verified/);
  else {
    assert.equal(posts[0].account_key,'internal-account-key');
    assert.equal(posts[0].ebay_order_id,'order-123');
  }
}
(async()=>{await run(); await run(true); console.log('Profit worker: capture, distinct seller identity, timeout and cleanup passed');})().catch(e=>{console.error(e);process.exitCode=1;});
