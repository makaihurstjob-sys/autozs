(async()=>{const t=await chrome.tabs.duplicate(851665504);await chrome.tabs.update(t.id,{url:supplierTrackingRunnerUrl({external_order_id:'WK37553521'}),active:false});return {id:t.id};})()
