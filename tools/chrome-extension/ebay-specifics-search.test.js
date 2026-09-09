const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(`${__dirname}/ebay-fill.js`,'utf8');
let expanded=false,selected='',search='';
const input={};
const trigger={innerText:'',getAttribute:()=>expanded?'true':'false',click:()=>{expanded=!expanded;}};
const wrong={innerText:'Adjustable Wrench',click:()=>{throw Error('Unrelated first page option');}};
const right={innerText:'Hand Cultivator/Grubber',click:()=>{selected='Hand Cultivator/Grubber';}};
const panel={querySelectorAll:s=>s.startsWith('input')?[input]:search==='Hand Cultivator/Grubber'?[right]:[wrong]};
const row={valueHost:{querySelectorAll:()=>[trigger]}};
const ctx={isVisible:()=>true,waitForCondition:async p=>p(),ebayItemSpecificOptionPanel:()=>expanded?panel:null,
 normalizeComparableValue:s=>String(s||'').toLowerCase().trim(),nearbyText:()=>'',delay:async()=>{},
 setEbayTextFieldValue:async(e,v)=>{assert.equal(e,input);search=v;},ebayItemSpecificRowValue:()=>selected};
vm.createContext(ctx);
const start=source.indexOf('async function chooseEbayItemSpecificOption(');
vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),ctx);
(async()=>{assert.equal(await ctx.chooseEbayItemSpecificOption(row,['Hand Cultivator/Grubber']),true);assert.equal(selected,'Hand Cultivator/Grubber');assert.equal(expanded,false);console.log('specifics search tests passed');})().catch(e=>{console.error(e);process.exitCode=1;});
