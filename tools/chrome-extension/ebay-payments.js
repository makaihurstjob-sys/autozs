/* Read-only capture of the visible Seller Hub transaction list. */
function readEbayPayments(account, username) {
  if (location.hostname !== 'www.ebay.com' || location.pathname !== '/mes/transactionlist') return null;
  const body = document.body?.innerText || '';
  if (!body.includes(`Seller Hub${username}`) && !body.includes(`Seller Hub\n${username}`)) return null;
  const filters = [...document.querySelectorAll('select')].map(e=>e.value).filter(v=>/^(STATUS_FILTER|TYPE_FILTER|DATE_FILTER)/.test(v));
  const count = body.match(/Transactions:\s*1-(\d+) of (\d+)/);
  if (!count || count[1] !== count[2]) throw Error('Transaction list has additional pages; full capture required.');
  const rows = [...document.querySelectorAll('.transaction--content-wrapper')].map(r=>({
    date:r.querySelector('.transactions-date')?.innerText.split('\n')[0],
    description:r.querySelector('.transaction--desc-row')?.innerText,
    detail_url:r.querySelector('.transaction--details a')?.href,
    amount:r.querySelector('.transaction--amount')?.innerText,
    fees:r.querySelector('.transaction--fees')?.innerText,
    net:r.querySelector('.transaction--net .BOLD')?.textContent,
    express_fee:r.innerText.match(/\$[\d,.]+ Express payout fee/)?.[0] || null
  }));
  return {account_key:account, source_url:location.href, filters, rows, count:Number(count[2]),
    hide_listing_fees:document.querySelector('input[aria-label="Hide listing fees"]')?.checked,
    search:document.querySelector('#search-field')?.value,
    start_date:document.querySelector('#start_date')?.value, end_date:document.querySelector('#end_date')?.value};
}

let ebayPaymentsRunning = false;
async function reconcileEbayPayments() {
  if(ebayPaymentsRunning || !(await canRunAutozsWorkerJobs())) return;
  ebayPaymentsRunning=true;
  let ownedTab=null;
  try {
    const account=await matchedEbayAccountKey();if(!account)return;
    const key='autozsPaymentsCheck:'+account;
    const prior=(await chrome.storage.local.get(key))[key];
    if(prior?.nextCheck > Date.now())return;
    const identity=await localApiJson(`/ebay/browser-account?account_key=${encodeURIComponent(account)}`);
    if(!identity?.can_list || !identity.expected_username)return;
    try {
      const tabs=await chrome.tabs.query({url:'https://www.ebay.com/mes/transactionlist*'});
      const tab=tabs[0] || await chrome.tabs.create({url:'https://www.ebay.com/mes/transactionlist?sh=true',active:false});
      if(!tabs.length)ownedTab=tab.id;
      let observation=null;
      for(let i=0;i<20;i++){
        const result=await chrome.scripting.executeScript({target:{tabId:tab.id},func:readEbayPayments,args:[account,identity.expected_username]});
        observation=result[0]?.result;if(observation)break;
        await new Promise(r=>setTimeout(r,1000));
      }
      if(!observation)throw Error('Payments page unavailable or seller identity not verified.');
      const result=await localApiJson('/finance/ebay-payments/capture',{method:'POST',body:JSON.stringify(observation)});
      await chrome.storage.local.set({[key]:{status:result.status,lastChecked:Date.now(),nextCheck:Date.now()+6*60*60*1000}});
    }catch(error){
      await localApiJson('/finance/ebay-payments/failure',{method:'POST',body:JSON.stringify({account_key:account,error:String(error.message || error)})}).catch(()=>{});
      await chrome.storage.local.set({[key]:{status:'needs_review',error:String(error.message || error),nextCheck:Date.now()+30*60*1000}});
      throw error;
    }
  }finally{
    if(ownedTab)await chrome.tabs.remove(ownedTab).catch(()=>{});
    ebayPaymentsRunning=false;
  }
}
