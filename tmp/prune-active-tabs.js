(async()=>({tabs:(await chrome.tabs.query({url:'https://www.ebay.com/sh/lst/*'})).map(t=>({id:t.id,url:t.url})),pause:await localApiJson('/listing-jobs/automation-pause')}))()
