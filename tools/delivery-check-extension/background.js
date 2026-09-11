const API = 'http://127.0.0.1:8000/delivery-quotes';
const STATE = 'deliveryCheckState';
const CART = 'https://www.homedepot.com/mycart/home';
let polling = false;

async function api(path, body) {
  let response;
  try { response = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); }
  catch { const error = Error('Delivery API temporarily unavailable'); error.retryable = true; throw error; }
  if (!response.ok) { const error = Error(`Delivery API ${response.status}`); error.retryable = response.status >= 500; throw error; }
  return response.json();
}
async function save(state) { await chrome.storage.local.set({ [STATE]: state }); }
function lease(state) { return { worker_id: state.workerId, lease_token: state.job.lease_token }; }
async function page(state, action) {
  await chrome.scripting.executeScript({ target: { tabId: state.tabId }, files: ['cart-quotes.js', 'page.js'] });
  const result = await chrome.scripting.executeScript({ target: { tabId: state.tabId }, args: [action, state.job],
    func: (action, job) => autozsDeliveryPage(action, job) });
  if (result.length !== 1 || !result[0].result) throw Error('Missing delivery page evidence');
  return result[0].result;
}
async function transition(state, phase) { state.phase = phase; state.phaseAt = Date.now(); await save(state); }

async function deliveryTick() {
  if (polling) return;
  polling = true;
  let state;
  try {
    const stored = await chrome.storage.local.get([STATE, 'deliveryWorkerId', 'deliveryInspectionUntil']);
    if (Number(stored.deliveryInspectionUntil || 0) > Date.now()) return;
    state = stored[STATE];
    if (state?.paused) return;
    const workerId = stored.deliveryWorkerId || `delivery-${crypto.randomUUID()}`;
    if (!stored.deliveryWorkerId) await chrome.storage.local.set({ deliveryWorkerId: workerId });
    if (!state) {
      // A leftover HD tab is not ours to repurpose or close.
      const tabs = await chrome.tabs.query({ url: 'https://www.homedepot.com/*' });
      if (tabs.length) { await save({ paused: true, message: 'Existing Home Depot tab preserved; review isolated profile' }); return; }
      const job = await api('/jobs/claim', { worker_id: workerId });
      if (!job) return;
      state = { job, workerId, phase: 'initial', phaseAt: Date.now(), startedAt: Date.now() };
      await save(state);
      const tab = await chrome.tabs.create({ url: CART, active: false });
      state.tabId = tab.id;
      await save(state);
      return;
    }
    // Revalidate lease before every browser action, including recovery after a worker restart.
    try {
      const current = await api(`/jobs/${state.job.id}/heartbeat`, lease(state));
      if (current.status === 'completed' && state.phase === 'complete') {
        if (state.tabId) await chrome.tabs.remove(state.tabId);
        await save(null);
        return;
      }
    }
    catch (error) {
      // Network interruptions preserve progress. An expired lease never authorizes further clicks.
      if (String(error.message).includes('409')) await save({ ...state, paused: true, message: 'Delivery lease no longer valid; cart preserved' });
      return;
    }
    if (!state.tabId) throw Error('Interrupted tab creation; inspect isolated profile');
    if (Date.now() - state.startedAt > 8 * 60 * 1000) throw Error('Delivery check timed out; cart preserved');
    const tab = await chrome.tabs.get(state.tabId);
    if (tab.status !== 'complete') return;
    // Each render gets a settling interval; never use the pre-mutation quote.
    if (Date.now() - state.phaseAt < 4000) return;
    if (state.phase === 'initial') {
      const observed = await page(state, 'inspect');
      if (!observed.empty) throw Error('Guest cart was not empty; preserved for review');
      await transition(state, 'product');
      await chrome.tabs.update(state.tabId, { url: state.job.source_url });
    } else if (state.phase === 'product') {
      await page(state, 'prepare_product');
      await transition(state, 'prepared');
    } else if (state.phase === 'prepared') {
      // Persist BEFORE Add to Cart: a restart must not repeat an uncertain click.
      await transition(state, 'add_pending');
      await page(state, 'add');
    } else if (state.phase === 'add_pending') {
      await transition(state, 'cart');
      await chrome.tabs.update(state.tabId, { url: CART });
    } else if (state.phase === 'cart') {
      const observed = await page(state, 'inspect');
      if (!observed.cartMatches) throw Error('Added item was not confirmed; will not repeat Add to Cart');
      const quote = observed.quote;
      if (quote?.postal_code === state.job.postal_code && quote.quantity === 1) {
        const key = JSON.stringify(quote);
        if (state.previousQuote === key && Date.now() - state.quoteAt >= 3000) {
          state.quote = quote;
          await transition(state, 'remove_pending');
          await page(state, 'remove');
        } else { state.previousQuote = key; state.quoteAt = Date.now(); await save(state); }
      } else {
        state.previousQuote = null;
        await save(state);
        await page(state, 'zip');
        state.phaseAt = Date.now();
        await save(state);
      }
    } else if (state.phase === 'remove_pending') {
      const observed = await page(state, 'inspect');
      if (!observed.empty) throw Error('Test-item removal was not confirmed; cart preserved');
      await transition(state, 'complete');
    } else if (state.phase === 'complete') {
      // No browser mutation after this point. An uncertain API response is recovered by lease checks.
      await api(`/jobs/${state.job.id}/complete`, { ...lease(state), quote: state.quote, cart_cleared: true });
      await chrome.tabs.remove(state.tabId);
      await save(null);
    } else throw Error('Unknown delivery phase; cart preserved');
  } catch (error) {
    if (error.retryable) {
      await chrome.storage.local.set({ deliveryLastError: error.message });
      return;
    }
    if (state?.job && /Transient supplier page error/.test(String(error.message)) && (state.pageRetries || 0) < 3) {
      state.pageRetries = (state.pageRetries || 0) + 1;
      state.phaseAt = Date.now();
      await save(state);
      await chrome.tabs.reload(state.tabId);
      return;
    }
    if (state?.job) {
      const message = String(error.message || error).slice(0, 500);
      // Before add_pending this worker has never attempted an Add to Cart.
      // Let the server back off this product without stalling unrelated checks.
      const safeRetry = /Transient supplier page error/.test(message) &&
        ['initial', 'product', 'prepared'].includes(state.phase);
      if (safeRetry) {
        try {
          await api(`/jobs/${state.job.id}/failed`, { ...lease(state), message, retryable: true });
          await chrome.tabs.remove(state.tabId);
          await save(null);
          return;
        } catch {
          await save({ ...state, paused: true, message: 'Could not confirm delivery retry or tab cleanup; review isolated profile' });
          return;
        }
      }
      try { await api(`/jobs/${state.job.id}/failed`, { ...lease(state), message, retryable: false }); } catch {}
      await save({ ...state, paused: true, message });
    } else await chrome.storage.local.set({ deliveryLastError: String(error.message || error) });
  } finally { polling = false; }
}

chrome.alarms.create('delivery-check', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'delivery-check') deliveryTick(); });
chrome.tabs.onUpdated.addListener((_id, change) => { if (change.status === 'complete') setTimeout(deliveryTick, 5000); });
chrome.runtime.onStartup.addListener(deliveryTick);
chrome.runtime.onInstalled.addListener(deliveryTick);
