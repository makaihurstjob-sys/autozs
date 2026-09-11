# Posting recovery audit — September 11, 2026

Base: 23fcd18. Branch: agents/posting-20260911. Audit only.

## Finding: preserve uncertainty after the final listing click

Missing browser confirmation does not establish rejection. Current code nevertheless reports that the listing is still a draft and invites retry after a final click without a visible error. Duplicate submission is a risk, **not a reproduced incident or proven end-to-end duplicate path**.

Evidence in tools/chrome-extension/ebay-fill.js:

- Lines 1688–1690 invoke the final click and wait for navigation, button disappearance, confirmation, or error.
- Lines 1700–1712 time out confirmation and return ok:false with “so it is still a draft” and “Review the draft and retry,” without authoritative rejection evidence.
- Lines 1294–1303 turn that result into needs_review / failed.
- Line 1306 records submitting only after submitScheduledListing returns ok:true. A crash/navigation between click and that write has no newly persisted submitting marker from this path.

This audit reproduces local misclassification and identifies persistence ordering; it does not characterize every background recovery rule.

## Validation performed

Inspected ebay-schedule-refresh.test.js: source extraction into a Node VM, mocked persistence/delay, no network/database. Ran `node tools/chrome-extension/ebay-schedule-refresh.test.js`: `schedule refresh tests passed`.

Exact additional command, run from the assigned worktree in PowerShell:

```powershell
@'
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const source=fs.readFileSync('tools/chrome-extension/ebay-fill.js','utf8');
const start=source.indexOf('async function submitScheduledListing(');
const fn=source.slice(start,source.indexOf('\n}',start)+2);
let clicks=0;
const ctx={ensureListingScheduleStable:async()=>true,criticalListingCheckDetails:()=>[{label:'item specifics',ok:true}],detectEbaySubmissionIssue:()=>'',findFinalScheduleButton:()=>({}),delay:async()=>{},location:{href:'https://www.ebay.com/lstng?draftId=123'},clickPrelistElementAndWait:async()=>{clicks++;return true;},waitForCondition:async predicate=>predicate(),detectEbayPublishConfirmation:()=>null,isEbayListingEditorPage:()=>true,describeUnconfirmedSubmission:()=>''};
vm.createContext(ctx);vm.runInContext(fn,ctx);
(async()=>{const result=await ctx.submitScheduledListing({listing_schedule_at:'2026-09-12T12:00:00'},1);assert.equal(clicks,1);assert.equal(result.ok,false);assert.match(result.message,/still a draft/);assert.match(result.message,/retry/);console.log(JSON.stringify({clicks,result}));})().catch(e=>{console.error(e);process.exitCode=1;});
'@ | node
```

Result (exit 0):

```json
{"clicks":1,"result":{"ok":false,"message":"eBay never confirmed the scheduled listing after the final click, so it is still a draft. eBay showed no visible error. Review the draft and retry."}}
```

This executes only source text and mocks: valid fields, one click returning advancement, editor remaining visible, no confirmation/error, and immediate predicate evaluation instead of waiting. No browser or AUTOZS access.

## Safe implementation plan

1. Persist an attempt marker with job/draft identity immediately before the final click; fail closed if persistence fails.
2. Distinguish pre-click failure, explicit rejection, and unknown post-click outcome. Unknown outcomes retain confirmation_pending and report unverified acceptance, without claiming the item remains a draft.
3. On reload/recovery, reconcile a pending attempt before permitting another final click. Inspect background retry behavior before selecting the backend/browser state representation.
4. Add isolated tests for crash immediately after click, no confirmation with editor visible, unrelated navigation, delayed authoritative confirmation, and marker-save failure. Assert unresolved attempts never click again and completed status requires authoritative evidence.
5. Run existing posting tests. Controlled live schedule correction/persistence remains coordinator work; mocks are not live validation.

No application edits, operational browser/API/database access, extension reloads, or real submissions occurred.
