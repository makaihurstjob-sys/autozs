(async()=>{const t=await chrome.tabs.create({url:'https://www.homedepot.com/cart?autozs_supplier_order=4&autozs_checkout_canary=1',active:true});return {tabId:t.id};})()
