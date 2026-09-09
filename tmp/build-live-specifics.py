import json,pathlib,urllib.request
s=pathlib.Path('tools/chrome-extension/ebay-fill.js').read_text(encoding='utf-8-sig')
names=['itemSpecificMatches','fillRequiredEbayItemSpecifics','inferredItemSpecifics']
parts=[]
for name in names:
 start=s.index('function '+name+'(')
 if s[max(0,start-6):start]=='async ': start-=6
 end=s.index('\n}',start)+2
 parts.append(s[start:end])
pkg=json.load(urllib.request.urlopen('http://127.0.0.1:8000/products/104/ebay-package'))
expr='(async()=>{const t=(await chrome.tabs.query({url:"https://www.ebay.com/lstng*"}))[0];return await chrome.scripting.executeScript({target:{tabId:t.id},func:async()=>{'+ '\n'.join(parts)+'\nconst pkg='+json.dumps(pkg)+';if(!document.title.includes("50 ft."))throw Error("Wrong draft title");return {filled:await fillRequiredEbayItemSpecifics(pkg),type:document.querySelector(\'button[name="attributes.Type"]\')?.innerText, matches:itemSpecificMatches("Type","Standard Garden Hose")};}})})()'
pathlib.Path('tmp/test-specifics-live.js').write_text(expr)
