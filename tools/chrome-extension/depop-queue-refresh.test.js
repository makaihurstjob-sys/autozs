const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(`${__dirname}/../../apps/local_dashboard/index.html`, 'utf8');
const dashboard = { URL, marketplaceMode: 'depop', state: {
  depopVariants: [{ product_id: 20 }, { product_id: 30 }],
  captureQueue: { items: [{ product_id: 10 }, { product_id: 20 }] },
  ebayListings: [{product_id: 30}],
  listingJobs: [{product_id: 10,kind:'Listing'}],
  sourceRefreshJobs: [{product_id:10,kind:'Price refresh'}, {product_id:20,kind:'Price refresh'}, {product_id:30,kind:'Price refresh'}],
  ebayRevisionJobs: [{kind:'Revision'}], ebayRevisionBatches: [{kind:'Revision batch'}],
  depopJobs: [{product_id:20,kind:'Depop listing'}],
}, jobActivityGroupSort:()=>0, jobActivityTimeValue:()=>0, latestSourceRefreshJobs:jobs=>jobs };
for (const name of ['productCaptureActivityEntry','listingJobActivityEntry','sourceRefreshJobActivityEntry','ebayRevisionJobActivityEntry','ebayRevisionBatchActivityEntry','depopJobActivityEntry']) dashboard[name] = job => ({ ...job, group:'queued' });
vm.createContext(dashboard);
vm.runInContext(html.slice(html.indexOf('      function jobActivityEntries()'), html.indexOf('      function depopJobActivityEntry(')),dashboard);
let entries = dashboard.jobActivityEntries();
assert.equal(entries.length,4);
assert.ok(entries.every(entry=>[20,30].includes(entry.product_id)));
assert.ok(!entries.some(entry=>entry.kind?.startsWith('Revision')));
dashboard.marketplaceMode='ebay';
entries=dashboard.jobActivityEntries();
assert.ok(!entries.some(entry=>entry.kind==='Depop listing' || entry.product_id===20));
assert.ok(entries.some(entry=>entry.product_id===30),'shared products show in both marketplaces');
vm.runInContext(html.slice(html.indexOf('      function jobActivityWorkloadCounts('),html.indexOf('      function jobActivityImportantCount(')),dashboard);
assert.equal(dashboard.jobActivityWorkloadCounts([{kind:'Depop listing',group:'queued'}]).listings,1);

const background=fs.readFileSync(`${__dirname}/background.js`,'utf8');
const opened=[]; let tabs=[];
const runner={ URL, chrome:{tabs:{query:async()=>tabs,create:async tab=>opened.push(tab),update:async(id,tab)=>opened.push({id,...tab})}},stampedHomeDepotWorkerUrl:url=>url };
vm.createContext(runner);
vm.runInContext(background.slice(background.indexOf('function isSourceRefreshRunnerUrl('),background.indexOf('async function openNextSourceRefreshJob(')),runner);
assert.equal(runner.isSourceRefreshRunnerUrl('https://www.amazon.com/dp/A?autozs_refresh_job=2'),true);
assert.equal(runner.isSourceRefreshRunnerUrl('https://evil.example/?autozs_refresh_job=2'),false);
assert.equal(runner.isSourceRefreshRunnerUrl('https://www.amazon.com/dp/A'),false);
(async()=>{
  await runner.openSourceRefreshRunnerUrl('https://www.amazon.com/dp/A?autozs_refresh_job=2');
  assert.equal(opened[0].active,false);
  tabs=[{id:9,url:'https://www.amazon.com/dp/A?autozs_refresh_job=2'}];
  await runner.openSourceRefreshRunnerUrl('https://www.homedepot.com/p/A?autozs_refresh_job=3');
  assert.equal(opened[1].id,9,'reuse the source runner to avoid concurrent capture tabs');
  console.log('PASS marketplace queue scoping, shared products, Depop workload counts and Amazon source runner');
})().catch(error=>{console.error(error);process.exitCode=1});
