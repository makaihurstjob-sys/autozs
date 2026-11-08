const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/background.js`, 'utf8');
const url = 'https://www.amazon.com/dp/B012345678?ea_auto_import=1&autozs_refresh_job=12&autozs_worker_opened_at=1';
const personal = {id: 1, url: 'https://www.amazon.com/dp/PERSONAL'};
let tabs = [], removed = [], created = 0, updates = 0, failRemove = false, failCreate = false;
const storage = {};
const ctx = {
  URL, Date, AbortSignal, supplierTabOpenBusy: false, productCaptureDispatchBusy: false,
  SUPPLIER_RUNNER_SLOT_KEY: 'slot', AUTOZS_WORKER_OPENED_AT_PARAM: 'autozs_worker_opened_at',
  HOME_DEPOT_WORKER_TAB_MAX_AGE_MS: 900000,
  chrome: {storage: {session: {get: async key => ({[key]: storage[key]}), set: async values => Object.assign(storage, values)}}, tabs: {
    query: async () => tabs,
    create: async args => {if (failCreate) throw Error('create failed'); created++; const tab={id:100+created,...args}; tabs.push(tab); return tab;},
    update: async (id,args) => {updates++; const tab=tabs.find(t=>t.id===id); Object.assign(tab,args); return tab;},
    remove: async id => {if(failRemove) throw Error('close failed'); removed.push(id); tabs=tabs.filter(t=>t.id!==id);},
  }},
  localApiJson: async () => {throw Error('offline');},
};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function isProductCaptureRunnerUrl('), source.indexOf('async function hasRunningListingJob(')), ctx);
(async () => {
  tabs=[personal,{id:2,url},{id:3,url}];
  await ctx.openSourceRefreshRunnerUrl(url);
  assert.deepEqual(removed,[3]); assert.equal(updates,1); assert.equal(created,0);
  assert.ok(tabs.includes(personal));
  tabs=[personal]; delete storage.slot;
  await Promise.all(Array.from({length:20},()=>ctx.openSourceRefreshRunnerUrl(url)));
  assert.equal(created,1,'concurrent callers have one slot');
  tabs[1].url='https://amazon.com/dp/B012345678';
  await ctx.openSourceRefreshRunnerUrl(url);
  assert.equal(created,1,'redirect without marker reuses remembered tab');
  await ctx.cleanupStaleHomeDepotWorkerTabs(Date.now()+900001);
  assert.equal(tabs.length,1,'timeout closes redirected tab even when API is offline');
  assert.equal(tabs[0],personal);
  delete storage.slot; tabs=[personal,{id:4,pendingUrl:url}];
  await ctx.openSourceRefreshRunnerUrl(url);
  assert.equal(created,1,'pending navigation occupies slot');
  tabs=[personal,{id:4,url},{id:5,url}]; failRemove=true;
  await assert.rejects(ctx.openSourceRefreshRunnerUrl(url),/close failed/);
  assert.equal(created,1,'failed removal cannot increase count'); failRemove=false;
  tabs=[personal]; delete storage.slot; failCreate=true;
  await assert.rejects(ctx.openSourceRefreshRunnerUrl(url),/create failed/);
  failCreate=false; await ctx.openSourceRefreshRunnerUrl(url);
  assert.equal(created,2,'opening lock releases after error');
  const owned=tabs[1]; owned.url='https://dash.lucidtrading.com/';
  await ctx.cleanupStaleHomeDepotWorkerTabs(Date.now()+900001);
  assert.ok(tabs.includes(owned),'ownership never follows tab to another site');
  assert.equal(ctx.isSourceRefreshRunnerUrl('http://www.amazon.com/?autozs_refresh_job=2'),false);
  assert.equal(ctx.isSourceRefreshRunnerUrl('https://www.amazon.com.evil/?autozs_refresh_job=2'),false);
  tabs=[personal]; delete storage.slot;
  let claims=0;
  Object.assign(ctx, {
    PRODUCT_CAPTURE_LAST_OPENED_KEY:'captureOpened', SOURCE_REFRESH_LAST_OPENED_KEY:'refreshOpened',
    PRODUCT_CAPTURE_MIN_GAP_MS:15000, SOURCE_REFRESH_MIN_GAP_MS:75000,
    canRunAutozsSourceJobs:async()=>true, productCaptureWorkerId:async()=>'test-worker',
    hasRunningSourceRefreshJob:async()=>false,
    localApiJson:async path=>{
      if(path==='/source-refresh/jobs/running') return {running:false};
      if(path==='/source-refresh/jobs') return [];
      claims++; return {product_id:5,source_url:'https://www.amazon.com/dp/B012345678'};
    },
  });
  ctx.chrome.storage.local=ctx.chrome.storage.session;
  await Promise.all([ctx.openNextProductCapture(),ctx.openNextSourceRefreshJob()]);
  assert.equal(claims,1,'capture and refresh alarms share the dispatch lock');
  assert.equal(tabs.length,2,'one worker tab plus personal tab');
  for (const marker of ['autozs_capture_product_id=5&ea_auto_import=1', 'autozs_refresh_job=12']) {
    tabs=[personal]; delete storage.slot;
    await ctx.openManagedSupplierRunner('https://www.amazon.com/dp/TEST?'+marker);
    const managed=tabs[1];
    managed.url='https://www.amazon.com/dp/TEST';
    assert.equal(await ctx.closeManagedSupplierRunner(managed),true,'completion releases redirected capture/refresh slot');
    assert.deepEqual(tabs,[personal],'no leaked tab after completion');
  }
  tabs=[personal]; delete storage.slot;
  assert.equal(await ctx.closeManagedSupplierRunner(personal),false,'personal Amazon page cannot close');
  await ctx.openManagedSupplierRunner(url);
  const navigated=tabs[1]; navigated.url='https://lucidtrading.com/dashboard/';
  assert.equal(await ctx.closeManagedSupplierRunner(navigated),false,'late completion preserves owner navigation');
  tabs=[personal]; delete storage.slot;
  await ctx.openManagedSupplierRunner(url);
  let ackStarted=false, releaseAck;
  ctx.localApiJson=async()=>{ackStarted=true;await new Promise(resolve=>{releaseAck=resolve});};
  const sweep=ctx.cleanupStaleHomeDepotWorkerTabs(Date.now()+900001);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(ackStarted,true);
  assert.deepEqual(tabs,[personal],'timeout closes before stalled API acknowledgement');
  releaseAck(); await sweep;
  const pauseSource=source.slice(source.indexOf('async function canRunAutozsSourceJobs('),source.indexOf('async function clearHomeDepotBatchState('));
  vm.runInContext(pauseSource,ctx);
  ctx.isWindowsPlatform=()=>true;
  ctx.HOME_DEPOT_SOURCE_WORKER_PAUSED_KEY='paused';
  for(const mode of ['operations','capture']) {
    ctx.readAutozsWorkerMode=async()=>mode;
    storage.paused=true; assert.equal(await ctx.canRunAutozsSourceJobs(),false);
    storage.paused=false; assert.equal(await ctx.canRunAutozsSourceJobs(),true);
  }
  console.log('PASS supplier tab cap, reuse, concurrency, redirects, pending navigation, timeout/offline recovery, failure locks and personal tabs');
})().catch(error=>{console.error(error);process.exitCode=1;});
