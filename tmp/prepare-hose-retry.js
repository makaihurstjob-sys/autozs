(async()=>{
 if(await hasRunningListingJob()) throw Error('A listing job is running');
 const job=await (await fetch('http://127.0.0.1:8000/listing-jobs/312')).json();
 if(job.product_id!==104 || job.status!=='needs_review' || job.ebay_draft_id!=='5165842996402') throw Error('Job identity changed');
 const source=await (await fetch(chrome.runtime.getURL('ebay-fill.js'))).text();
 if(!source.includes('if (input && /search-box|extracted-attribute-selector/')) throw Error('Row fix missing');
 const tabs=await chrome.tabs.query({url:'https://www.ebay.com/lstng*'});
 for(const t of tabs){if(!t.url.includes('draftId=5165842996402'))throw Error('Unexpected editor'); await chrome.tabs.remove(t.id);}
 return {fixLoaded:true,closedFailedDraft:tabs.length};
})()
