// Durable publication follow-ups. These never create or re-post a listing.
const DEPOP_FOLLOWUP_ALARM = 'autozs-depop-postprocess';
async function runDepopFollowups() {
  const stored = await chrome.storage.local.get(['autozsDepopPostPolicy', 'autozsDepopPostprocess', 'autozsDepopPendingPublication']);
  if (!stored.autozsDepopPostPolicy?.postThenBoost || stored.autozsDepopPendingPublication) return;
  const entries = Object.values(stored.autozsDepopPostprocess || {});
  const due = entries.some(e => e.boost === 'pending' || e.offers === 'pending'
    || e.offers === 'submitting' || e.boost === 'submitting'
    || e.offers === 'enabled' && Date.parse(e.offerExpiresAt || '') <= Date.now()
    || e.offers === 'blocked' && Date.parse(e.retryAt || '') <= Date.now());
  if (!due) return;
  const tabs = await chrome.tabs.query({url:'https://www.depop.com/*'});
  const existing = tabs.find(t => t.url?.includes('autozs_depop_postprocess=1'));
  if (existing) return;
  await chrome.tabs.create({url:'https://www.depop.com/sellinghub/selling/active/?autozs_depop_postprocess=1', active:false});
}
if (globalThis.chrome?.alarms?.onAlarm) {
  chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === DEPOP_FOLLOWUP_ALARM) runDepopFollowups().catch(() => {}); });
  chrome.alarms.get(DEPOP_FOLLOWUP_ALARM).then(existing => {
    if (!existing) return chrome.alarms.create(DEPOP_FOLLOWUP_ALARM, {periodInMinutes:1});
  }).catch(() => {});
}
