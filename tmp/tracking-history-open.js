(async()=>{const t=await chrome.tabs.create({url:'https://www.homedepot.com/myaccount/purchase-history',active:false});return {id:t.id};})()
