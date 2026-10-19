(() => {
  if (globalThis.__AUTOZS_DEPOP_POSTPROCESS__) return;
  globalThis.__AUTOZS_DEPOP_POSTPROCESS__ = true;
  if (!location.pathname.startsWith('/sellinghub/selling/active')) return;
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const visible = e => !!e && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0;
  const text = e => String(e?.innerText || e?.textContent || '').trim();
  const api = async path => {
    const r = await chrome.runtime.sendMessage({type:'autozs-api-proxy',path,method:'GET'});
    if (!r?.ok) throw Error(r?.error || 'Post-processing API unavailable');
    return JSON.parse(r.body);
  };
  const save = async (id, changes) => {
    const data = (await chrome.storage.local.get('autozsDepopPostprocess')).autozsDepopPostprocess || {};
    if (!data[id]) throw Error('Follow-up record missing');
    data[id] = {...data[id], ...changes, updatedAt:new Date().toISOString()};
    await chrome.storage.local.set({autozsDepopPostprocess:data});
  };
  function exactButton(root, label) { return [...root.querySelectorAll('button,[role="button"],[role="menuitem"]')].find(e => visible(e) && !e.disabled && text(e) === label); }
  async function waitFor(fn, timeout=8000) {
    const end=Date.now()+timeout;
    while (Date.now()<end) {const result=fn();if(result)return result;await wait(200);}
    return null;
  }
  const dialog = () => [...document.querySelectorAll('[role="dialog"]')].find(visible);
  function closeDialog() {
    const modal=dialog(); if (!modal)return;
    const button=modal.querySelector('button[aria-label*="close" i]') || [...modal.querySelectorAll('button')].find(e=>!text(e));
    button?.click();
  }
  async function menu(row) {
    closeDialog();
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    await wait(100);
    const button=[...row.querySelectorAll('button')].find(e=>text(e)==='Manage');
    if(!button)throw Error('Exact listing Manage control missing');
    button.click();await wait(250);
    return [...document.querySelectorAll('[role="menu"]')].find(visible) || document;
  }
  function approvedBoostRate(modal) {
    const rates=[...text(modal).matchAll(/(\d+(?:\.\d+)?)\s*%/g)].map(m=>Number(m[1]));
    return rates.length>0 && rates.every(rate=>rate===12);
  }
  async function boost(row, entry) {
    let root=await menu(row);
    if(exactButton(root,'Unboost') || exactButton(root,'Unboost listing')) return 'done';
    if(entry.boost==='submitting')throw Error('Boost outcome is uncertain; read-only reconciliation did not confirm it');
    const open=exactButton(root,'Boost') || exactButton(root,'Boost listing');
    if(!open)throw Error('Boost control unavailable');
    open.click();
    const modal=await waitFor(dialog);
    if(!modal || !approvedBoostRate(modal)) {closeDialog();throw Error('Boost confirmation does not verify the approved 12% fee');}
    const confirm=exactButton(modal,'Boost listing') || exactButton(modal,'Boost');
    if(!confirm)throw Error('Unique Boost confirmation missing');
    await save(entry.listingId,{boost:'submitting'});
    confirm.click();await wait(1200);
    root=await menu(row);
    if(!exactButton(root,'Unboost') && !exactButton(root,'Unboost listing'))throw Error('Boost result is unconfirmed; will not submit again');
    return 'done';
  }
  function fill(input,value) {
    const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
    setter.call(input,String(value));input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
  }
  async function offers(row,entry) {
    const plan=await api(`/depop/variants/${entry.variantId}/offer-plan`);
    const root=await menu(row), open=exactButton(root,'Auto-send offers');
    if(!open)throw Error('Native automatic offers control missing');
    open.click(); const modal=await waitFor(dialog);
    if(!modal)throw Error('Automatic offers dialog missing');
    await waitFor(()=>modal.querySelector('#offer__price__input') && modal.querySelectorAll('input[type="checkbox"]').length===1);
    const input=modal.querySelector('#offer__price__input'), checks=[...modal.querySelectorAll('input[type="checkbox"]')];
    if(!input || checks.length!==1)throw Error('Ambiguous automatic offer controls');
    const checkbox=checks[0], done=exactButton(modal,'Done');
    if(!done)throw Error('Offer save control missing');
    if(!plan.enabled) {
      // No future automatic offers are permitted without cost evidence.
      if(checkbox.checked){checkbox.click();done.click();await wait(400);} else closeDialog();
      return {offers:'blocked',offerReason:plan.reason,retryAt:new Date(Date.now()+6*3600000).toISOString()};
    }
    if(plan.listing_id!==entry.listingId || Number(plan.listed_price)!==Number(entry.price)
      || !(plan.net_margin>=.25) || !(plan.offer_price>=plan.minimum_offer_price))throw Error('Offer plan identity/margin mismatch');
    if(checkbox.checked && Number(input.value)===Number(plan.offer_price)) {closeDialog();return {offers:'enabled',offerPrice:plan.offer_price,offerExpiresAt:plan.evidence_expires_at};}
    if(checkbox.checked)checkbox.click();
    fill(input,Number(plan.offer_price).toFixed(2));await wait(200);
    checkbox.click();await wait(200);
    const recheck=await api(`/depop/variants/${entry.variantId}/offer-plan`);
    if(!recheck.enabled || recheck.offer_price!==plan.offer_price || !checkbox.checked || Number(input.value)!==plan.offer_price)throw Error('Offer evidence changed before save');
    await save(entry.listingId,{offers:'submitting',offerPrice:plan.offer_price});
    done.click();await wait(700);
    // Read saved settings rather than treating a click as success.
    const verifyRoot=await menu(row);exactButton(verifyRoot,'Auto-send offers')?.click();
    const verify=await waitFor(dialog);
    const savedInput=verify?.querySelector('#offer__price__input'), savedCheck=verify?.querySelector('input[type="checkbox"]');
    if(!savedCheck?.checked || Number(savedInput?.value)!==plan.offer_price)throw Error('Automatic offer save unconfirmed');
    closeDialog();
    return {offers:'enabled',offerPrice:plan.offer_price,offerExpiresAt:plan.evidence_expires_at};
  }
  let busy=false;
  async function run() {
    if(busy)return;busy=true;
    try {
      const policy=(await chrome.storage.local.get('autozsDepopPostPolicy')).autozsDepopPostPolicy;
      if(!policy?.postThenBoost)return;
      const entries=Object.values((await chrome.storage.local.get('autozsDepopPostprocess')).autozsDepopPostprocess||{});
      const variants=await api('/depop/variants');
      for(const entry of entries) {
        const variant=variants.find(v=>v.id===entry.variantId && v.depop_listing_id===entry.listingId);
        if(!variant || !['published','active'].includes(variant.status))continue;
        const likes=[...document.querySelectorAll('header a[aria-label="Likes"], nav a[aria-label="Likes"]')];
        if(!likes.some(link=>new URL(link.href).pathname===`/${entry.username}/likes/`))throw Error('Signed-in account identity unverified');
        const row=await waitFor(()=>[...document.querySelectorAll('li:has(a[href*="/products/"][href*="/manage/"])')].find(e=>[...e.querySelectorAll('a')].some(a=>new URL(a.href).pathname===`/products/${entry.listingId}/manage/`)));
        if(!row || !text(row).includes(entry.title)) {await save(entry.listingId,{error:'Exact active listing not found'});continue;}
        try {
          if(entry.boost==='pending' || entry.boost==='submitting')await save(entry.listingId,{boost:await boost(row,entry),error:null});
        }catch(error){
          const latest=(await chrome.storage.local.get('autozsDepopPostprocess')).autozsDepopPostprocess?.[entry.listingId];
          await save(entry.listingId,{boost:latest?.boost==='submitting'?'submitting':'blocked',error:error.message});
        }
        if(policy.autoOffers && (entry.offers!=='blocked' || Date.parse(entry.retryAt||'')<=Date.now())
          && (entry.offers!=='enabled' || Date.parse(entry.offerExpiresAt||'')<=Date.now())) {
          try{await save(entry.listingId,await offers(row,entry));}
          catch(error){closeDialog();
            const latest=(await chrome.storage.local.get('autozsDepopPostprocess')).autozsDepopPostprocess?.[entry.listingId];
            await save(entry.listingId,{offers:latest?.offers==='submitting'?'submitting':'blocked',offerError:error.message,retryAt:new Date(Date.now()+6*3600000).toISOString()});}
        }
      }
    } finally {busy=false;document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));}
  }
  globalThis.AutoZSDepopPostprocess={run,approvedBoostRate};
  run().catch(()=>{});
  setInterval(()=>run().catch(()=>{}),60000);
})();
