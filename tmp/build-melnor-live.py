import json,urllib.request
from pathlib import Path
s=Path('tools/chrome-extension/ebay-fill.js').read_text(encoding='utf-8-sig');parts=[]
for name in ['revealEbayItemSpecifics','requiredItemSpecificsSatisfied','ebayItemSpecificRowValue','fillRequiredEbayItemSpecifics','inferredItemSpecifics','itemSpecificMatches']:
 start=s.index('function '+name+'(')
 if s[start-6:start]=='async ':start-=6
 parts.append(s[start:s.index('\n}',start)+2])
pkg=json.load(urllib.request.urlopen('http://127.0.0.1:8000/products/166/ebay-package'))
expr='''(async()=>{if(await hasRunningListingJob())throw Error('Running job');const t=(await chrome.tabs.query({url:'https://www.ebay.com/lstng*'}))[0];return chrome.scripting.executeScript({target:{tabId:t.id},func:async()=>{try{'''+ '\n'.join(parts)+'''
if(!location.href.includes('draftId=5165219480001')||!document.title.includes('Faucet Adapter 2MQC'))throw Error('Wrong product');
const pkg='''+json.dumps(pkg)+''';await revealEbayItemSpecifics();const filled=await fillRequiredEbayItemSpecifics(pkg);return {filled,valid:requiredItemSpecificsSatisfied(),type:document.querySelector('button[name="attributes.Type"]')?.innerText,brand:document.querySelector('button[name="attributes.Brand"]')?.innerText};}catch(e){return {error:String(e)}}}});})()'''
Path('tmp/melnor-live-fix.js').write_text(expr)
