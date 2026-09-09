const fs=require('fs');
const vm=require('vm');
const assert=require('node:assert/strict');
const test=require('node:test');
const source=fs.readFileSync(`${__dirname}/background.js`,'utf8');
const fn=source.slice(source.indexOf('async function openNextSupplierTrackingCheck()'),source.indexOf('function ebayTrackingUploadRunnerUrl'));
test('operations polling rotates pending orders, respects per-order interval, and clears stale tabs',async()=>{
 const storage={};const opened=[];const removed=[];let tabs=[];
 const orders=[{id:1,supplier:'home_depot',status:'placed',external_order_id:'WK111111'},{id:2,supplier:'home_depot',status:'placed',external_order_id:'WK222222'}];
 const c={recordSupplierTrackingResult:async()=>{},Date,URL,SUPPLIER_TRACKING_LAST_OPENED_KEY:'last',SUPPLIER_TRACKING_BLOCKED_UNTIL_KEY:'blocked',SUPPLIER_TRACKING_MIN_GAP_MS:21600000,AUTOZS_WORKER_OPENED_AT_PARAM:'autozs_worker_opened_at',canRunAutozsCheckoutJobs:async()=>false,canRunAutozsWorkerJobs:async()=>true,localApiJson:async()=>orders,isSupplierTrackingRunnerUrl:u=>u.includes('autozs_tracking_poll=1'),supplierTrackingRunnerUrl:o=>'https://www.homedepot.com/order/view/orderdetails?orderId='+o.external_order_id,chrome:{tabs:{query:async()=>tabs,remove:async id=>removed.push(id),create:async t=>opened.push(t)},storage:{local:{get:async()=>storage,set:async x=>Object.assign(storage,x),remove:async k=>delete storage[k]}}}};
 vm.createContext(c);vm.runInContext(fn,c);
 await c.openNextSupplierTrackingCheck();await c.openNextSupplierTrackingCheck();await c.openNextSupplierTrackingCheck();
 assert.equal(opened.length,2);assert.ok(opened[0].url.includes('WK111111'));assert.ok(opened[1].url.includes('WK222222'));
 tabs=[{id:9,url:'https://www.homedepot.com/order/view/orderdetails?autozs_tracking_poll=1&autozs_worker_opened_at=1'}];
 await c.openNextSupplierTrackingCheck();assert.deepEqual(removed,[9]);
 c.canRunAutozsWorkerJobs=async()=>false;storage.autozsSupplierTrackingChecks={};await c.openNextSupplierTrackingCheck();assert.equal(opened.length,2);
});
test('pending supplier sign-in keeps one handoff and stops new tracking tabs',async()=>{
 const removed=[];
 const c={recordSupplierTrackingResult:async()=>{},URL,canRunAutozsCheckoutJobs:async()=>false,canRunAutozsWorkerJobs:async()=>true,chrome:{tabs:{query:async()=>[
 {id:1,url:'https://www.homedepot.com/auth/view/signin?redirect=/myaccount/purchase-history?orderId=WK123456&autozs_tracking_poll=1'},
 {id:2,url:'https://www.homedepot.com/auth/view/signin?redirect=%2Fmyaccount%2Fpurchase-history%3ForderId%3DWK222222%26autozs_tracking_poll%3D1'},
 {id:3,url:'https://www.homedepot.com/auth/view/signin?redirect=/checkout'}
 ],remove:async id=>removed.push(id),create:async()=>assert.fail('must not open another tab')}}};
 vm.createContext(c);vm.runInContext(fn,c);await c.openNextSupplierTrackingCheck();
 assert.deepEqual(removed,[2]);
});
test('tracking results persist bounded history without full URLs or tokens',async()=>{
 const storage={};const c={URL,Date,chrome:{storage:{local:{get:async()=>storage,set:async v=>Object.assign(storage,v)}}}};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('async function recordSupplierTrackingResult('),source.indexOf('async function openNextSupplierTrackingCheck()')),c);
 for(let i=0;i<25;i++) await c.recordSupplierTrackingResult('https://www.homedepot.com/myaccount/order-details?orderNumber=WK123456&encryptedOrderNumbers=secret','verified_no_tracking');
 assert.equal(storage['autozsTrackingResults:WK123456'].length,20);
 assert.ok(!JSON.stringify(storage).includes('secret'));
 await c.recordSupplierTrackingResult('https://www.homedepot.com/auth/view/signin?redirect=%2Fmyaccount%2Fpurchase-history%3ForderId%3DWK123456','sign_in_required');
 assert.equal(storage['autozsTrackingResults:WK123456'].at(-1).outcome,'sign_in_required');
});
