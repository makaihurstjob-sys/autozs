(async()=>{if(await hasRunningListingJob())throw Error('Listing job running');return await chrome.tabs.create({url:'https://www.ebay.com/sh/lst/active',active:false})})()
