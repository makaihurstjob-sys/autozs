const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/background.js`, 'utf8');
const start = source.indexOf('async function pollDepopScheduledJob()');
const end = source.indexOf('\nasync function ensureDepopMetricsTab()', start);
async function main() {
  let storage = {}, tabs = [], calls = [], opened = [], mode = true;
  let account = {key:'m4coq', enabled:true, writes_enabled:true};
  const job = {id:7,account_key:'m4coq',status:'running',runner_url:'https://www.depop.com/products/create/?autozs_fill=1&autozs_job_id=7&autozs_account_key=m4coq'};
  const context = {URL, DEPOP_SCHEDULER_KEY:'autozsDepopScheduler', depopSchedulerBusy:false,
    canRunAutozsWorkerJobs:async()=>mode,
    chrome:{storage:{local:{get:async()=>storage,set:async(value)=>Object.assign(storage,value)}},tabs:{query:async()=>tabs,create:async(x)=>opened.push(x)}},
    localApiJson:async(path)=>{calls.push(path);return path==='/depop/accounts'?[account]:{job};},
  };
  vm.createContext(context);
  vm.runInContext(source.slice(start,end),context);
  const poll = ()=>context.pollDepopScheduledJob();
  await poll(); assert.equal(calls.length,0,'disabled by default');
  storage.autozsDepopScheduler={enabled:true,accountKey:'m4coq'};
  mode=false;await poll(); assert.equal(calls.length,0,'viewer never claims');mode=true;
  storage.autozsDepopPendingPublication={jobId:1};await poll(); assert.equal(calls.length,0,'pending draft blocks');
  delete storage.autozsDepopPendingPublication;
  tabs=[{url:'https://www.depop.com/products/create/'}];await poll();assert.equal(calls.length,0,'existing manual draft blocks');tabs=[];
  account.writes_enabled=false;await poll();assert.equal(opened.length,0);assert.equal(calls.length,1);account.writes_enabled=true;
  calls=[];await poll();assert.equal(opened.length,1);assert.equal(calls[1],'/depop/jobs/next?account_key=m4coq');
  storage.autozsDepopPendingPublication={jobId:7,postClickedAt:new Date().toISOString()};
  await poll();assert.equal(opened.length,1,'first submission holds the next job');
  delete storage.autozsDepopPendingPublication;
  tabs=[{url:'https://www.depop.com/products/first-published-bag/'}];
  job.id=8;job.runner_url=job.runner_url.replace('autozs_job_id=7','autozs_job_id=8');
  await poll();assert.equal(opened.length,2,'confirmed first listing allows unattended second job');
  assert.ok(opened[1].url.includes('autozs_job_id=8'));
  job.account_key='other';await poll();assert.equal(opened.length,2,'cross-account response never opens');job.account_key='m4coq';
  job.runner_url='https://evil.example/';await poll();assert.equal(opened.length,2,'untrusted runner rejected');
  job.runner_url='https://www.depop.com/products/create/?autozs_fill=1&autozs_job_id=8&autozs_account_key=m4coq';
  storage.autozsDepopScheduler={enabled:true,accountKey:'m4coq',jobId:8};
  calls=[];opened=[];tabs=[];
  await poll();assert.equal(opened.length,1);assert.equal(calls[1],'/depop/jobs/next?account_key=m4coq&job_id=8');
  assert.equal(opened[0].active,true,'Depop virtual dropdown runner must be visible');
  assert.equal(storage.autozsDepopScheduler.claimStarted,true);
  await poll();assert.equal(opened.length,1,'durable one-shot never claims a second job');
  storage.autozsDepopScheduler={enabled:true,accountKey:'m4coq',jobId:6};
  await poll();assert.equal(opened.length,1,'wrong job response never opens');
  await poll();assert.equal(opened.length,1,'wrong response remains consumed');
  storage.autozsDepopScheduler={enabled:true,accountKey:'m4coq',jobId:0};
  calls=[];await poll();assert.equal(calls.length,0,'invalid scope fails closed');
  console.log('Depop scheduler tests passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
