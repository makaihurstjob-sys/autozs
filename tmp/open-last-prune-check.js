(async()=>{const t=await chrome.tabs.create({url:'https://www.ebay.com/sh/lst/active?keyword=800456008929',active:false});return {tabId:t.id};})()
