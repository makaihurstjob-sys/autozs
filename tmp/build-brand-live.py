from pathlib import Path
s=Path('tools/chrome-extension/ebay-fill.js').read_text(encoding='utf-8-sig')
parts=[]
for name in ['itemSpecificMatches','fillEbayItemSpecificRow']:
 start=s.index('function '+name+'(')
 if s[start-6:start]=='async ': start-=6
 parts.append(s[start:s.index('\n}',start)+2])
expr='(async()=>{if(await hasRunningListingJob())throw Error("Job running");const t=(await chrome.tabs.query({url:"https://www.ebay.com/lstng*"}))[0];return await chrome.scripting.executeScript({target:{tabId:t.id},func:async()=>{'+ '\n'.join(parts)+'\nif(!location.href.includes("mode=ReviseItem")||!location.href.includes("draftId=5167880600803") || document.querySelector('input[name="title"]')?.value!=="5/8 in. x 50 ft. Heavy-Duty Hose | FREE SHIPPING")throw Error("Wrong item");const row=ebayItemSpecificRows().find(r=>r.key==="Brand");return {filled:await fillEbayItemSpecificRow(row,"Husky"),brand:document.querySelector(\'button[name="attributes.Brand"]\')?.innerText};}});})()'
Path('tmp/fill-brand-live.js').write_text(expr)

