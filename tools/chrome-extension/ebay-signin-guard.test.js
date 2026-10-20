const fs=require('fs');
const vm=require('vm');
const assert=require('node:assert/strict');
const test=require('node:test');
const source=fs.readFileSync(`${__dirname}/background.js`,'utf8');
const guard=source.slice(source.indexOf('const EBAY_SIGNIN_BLOCKED_SINCE_KEY'),source.indexOf('async function matchedEbayAccountKey()'));
const opener=source.slice(source.indexOf('async function openNextEbayOrderSync()'),source.indexOf('}\n',source.indexOf('await chrome.storage.local.set({ [EBAY_ORDER_LAST_OPENED_KEY]'))+2);
function harness(tabs){
 const storage={};const removed=[];const created=[];let now=1_000_000;
 const c={URL,Date:{now:()=>now},EBAY_ORDER_LAST_OPENED_KEY:'last',canRunAutozsWorkerJobs:async()=>true,
  claimNextEbayOrderSync:async()=>({id:9,status:'running',runner_url:'https://www.ebay.com/sh/reports/downloads#autozs_sync_run=9&autozs_report_type=orders'}),
  isEbayOrderRunnerUrl:()=>false,
  chrome:{tabs:{query:async q=>tabs.filter(t=>t.url.startsWith(String(q.url).replace('*',''))&&!removed.includes(t.id)),remove:async id=>{removed.push(id)},create:async t=>{created.push(t)},reload:async()=>{},update:async()=>{}},
   storage:{local:{get:async()=>storage,set:async x=>Object.assign(storage,x),remove:async k=>{delete storage[k]}}}}};
 vm.createContext(c);vm.runInContext(guard+opener,c);
 return {c,storage,removed,created,advance:ms=>{now+=ms;storage.last=0;}};
}
const signin=id=>({id,url:`https://signin.ebay.com/ws/eBayISAPI.dll?SignIn&ru=https%3A%2F%2Fwww.ebay.com%2Fsh%2Freports%2Fdownloads#autozs_sync_run=${id}&autozs_report_type=orders`});
test('signed-out eBay keeps one sign-in tab and stops opening new runner tabs',async()=>{
 const h=harness([signin(1),signin(2),signin(3),{id:50,url:'https://signin.ebay.com/ws/eBayISAPI.dll?SignIn'}]);
 for(let i=0;i<10;i++){await h.c.openNextEbayOrderSync();h.advance(61_000);}
 assert.equal(h.created.length,0);
 assert.deepEqual(h.removed.sort(),[1,2]);
});
test('sign-in wait retries with one fresh tab after fifteen minutes',async()=>{
 const h=harness([signin(1)]);
 await h.c.openNextEbayOrderSync();assert.equal(h.created.length,0);
 h.advance(16*60*1000);await h.c.openNextEbayOrderSync();
 assert.deepEqual(h.removed,[1]);assert.equal(h.created.length,1);
});
test('signed-in eBay opens runner tabs normally',async()=>{
 const h=harness([]);await h.c.openNextEbayOrderSync();assert.equal(h.created.length,1);
});
