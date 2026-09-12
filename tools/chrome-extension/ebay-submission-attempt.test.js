const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/ebay-fill.js`, 'utf8');
const names = ['listingSubmissionIdentity', 'listingSubmissionKeys', 'readListingSubmissionAttempt', 'persistListingSubmissionAttempt', 'reconcileListingSubmissionAttempt', 'pendingListingSubmissionResult', 'submitScheduledListing', 'runAutoDraftWorkflow', 'fillEbayListingDraft', 'clickPrelistElementAndWait'];
const extracted = names.map(name => { const start = source.search(new RegExp(`(?:async )?function ${name}\\(`)); return source.slice(start, source.indexOf('\n}', start) + 2); }).join('\n');
function harness(store = {}, options = {}) {
  let clicks = 0;
  let workflow = { mode: 'create_draft', productId: 'p1', jobId: '1', accountKey: 'a1' };
  const updates = [];
  const ctx = { URLSearchParams, Date, Object, String, encodeURIComponent,
    readAutoWorkflowState: () => workflow, readAutozsParams: () => new URLSearchParams(options.params || ''),
    currentWorkflowJobId: () => workflow.jobId, updateListingJob: async (id, update) => updates.push({id, ...update}),
    writeAutoWorkflowState: update => options.workflowFail ? null : (workflow = {...workflow,...update}),
    readDraftIdFromUrl: () => 'draft1',
    chrome: { storage: { local: {
      get: async keys => { if (options.readFail) throw Error('read'); return Object.fromEntries([].concat(keys).map(k => [k, store[k]])); },
      set: async values => { if (options.saveFail) throw Error('save'); if (!options.silentSaveFail) Object.assign(store, values); },
    } } },
    ensureListingScheduleStable: async () => true, criticalListingCheckDetails: () => [{label:'item specifics',ok:true}],
    detectEbaySubmissionIssue: () => '', findFinalScheduleButton: () => ({click: () => { assert.ok(store['autozsListingSubmission:job:1']); clicks++; if(options.crash) throw Error('crash'); if(options.navigate) ctx.location.href='unrelated'; }}), delay: async () => {},
    location: {href:'editor'}, isVisible: () => true, detectEbayPublishConfirmation: () => options.confirmed ? {listingId:'123'} : null,
    clickEbayElement: async () => { clicks++; return true; },
    waitForCondition: async predicate => predicate(), describeUnconfirmedSubmission: () => '',
  };
  vm.createContext(ctx); vm.runInContext(extracted,ctx);
  ctx.clickPrelistElementAndWait = async () => { throw new Error('Retrying helper is forbidden for final submission'); };
  return {ctx, store, updates, clicks:()=>clicks, job:id=>workflow.jobId=id, run:()=>ctx.submitScheduledListing({listing_schedule_at:'2026-09-12T12:00:00'},1)};
}
(async () => {
  for (const options of [{}, {crash:true}, {navigate:true}]) {
    const first=harness({},options); const result=await first.run();
    assert.equal(result.pending,true); assert.equal(first.clicks(),1); assert.doesNotMatch(result.message,/still a draft|Review the draft and retry/);
    const restarted=harness(first.store); assert.equal((await restarted.run()).pending,true); assert.equal(restarted.clicks(),0);
    restarted.job('2'); assert.equal((await restarted.run()).pending,true); assert.equal(restarted.clicks(),0);
    assert.equal((await restarted.ctx.runAutoDraftWorkflow({})).terminal,true);
    assert.equal(restarted.updates[0].status,'needs_review');
    await assert.rejects(restarted.ctx.fillEbayListingDraft({}),/outcome is unverified/);
  }
  for(const options of [{saveFail:true},{silentSaveFail:true},{readFail:true},{workflowFail:true}]) { const h=harness({},options); assert.equal((await h.run()).ok,false); assert.equal(h.clicks(),0); }
  const h=harness({}, {confirmed:true}); assert.equal((await h.run()).ok,true);
  await h.ctx.reconcileListingSubmissionAttempt({productId:'p1',jobId:'1',accountKey:'a1'},{listingId:'123'});
  assert.equal(h.store['autozsListingSubmission:job:1'].status,'confirmed');
  assert.match((await h.run()).message,/already published/); assert.equal(h.clicks(),1);
  h.job('2'); assert.equal(await h.ctx.readListingSubmissionAttempt(),null);
  // A late confirmation for job 1 cannot overwrite a newer unresolved product attempt.
  h.store['autozsListingSubmission:product:a1:p1']={jobId:'2',productId:'p1'};
  await h.ctx.reconcileListingSubmissionAttempt({productId:'p1',jobId:'1',accountKey:'a1'},{listingId:'123'});
  assert.equal(h.store['autozsListingSubmission:product:a1:p1'].status,undefined);
  // Explicit URL identity wins over shared workflow state overwritten by another tab.
  const explicit=harness(h.store,{params:'autozs_product_id=p1&autozs_job_id=2&autozs_account_key=a1'});
  assert.equal((await explicit.ctx.readListingSubmissionAttempt()).jobId,'2');
  const otherAccount=harness(h.store,{params:'autozs_product_id=p1&autozs_job_id=3&autozs_account_key=a2'});
  assert.equal(await otherAccount.ctx.readListingSubmissionAttempt(),null);
  const background=fs.readFileSync(`${__dirname}/background.js`,'utf8');
  const start=background.indexOf('async function reopenOrphanedListingJob(');
  vm.runInContext(background.slice(start,background.indexOf('\n}',start)+2),h.ctx);
  assert.equal(await h.ctx.reopenOrphanedListingJob({id:1,assistant_url:'mock'}),false);
  h.store['autozsListingSubmission:job:2']={jobId:'2',productId:'p1'};
  assert.equal(await h.ctx.reopenOrphanedListingJob({id:2,assistant_url:'mock'}),false);
  console.log('submission attempt tests passed (restart, crash, navigation, persistence failures, confirmation, replacement)');
})().catch(error=>{console.error(error);process.exitCode=1;});
