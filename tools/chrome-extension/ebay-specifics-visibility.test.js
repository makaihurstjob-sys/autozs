const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(`${__dirname}/ebay-fill.js`,'utf8');
let rows=[],mounted=false,value='';
const heading={innerText:'ITEM SPECIFICS',scrollIntoView:()=>{mounted=true;rows=[{required:true}];}};
const ctx={document:{body:{innerText:'ITEM SPECIFICS'},querySelectorAll:()=>[heading]},
 ebayItemSpecificRows:()=>rows,ebayItemSpecificRowValue:()=>value,
 waitForCondition:async predicate=>Boolean(predicate())};
vm.createContext(ctx);
for(const name of ['requiredItemSpecificsSatisfied','revealEbayItemSpecifics']){
 let start=source.indexOf('function '+name+'(');if(source.slice(start-6,start)==='async ')start-=6;
 vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),ctx);
}
(async()=>{
 assert.equal(ctx.requiredItemSpecificsSatisfied(),false,'Unmounted controls cannot pass validation');
 assert.equal(await ctx.revealEbayItemSpecifics(),true);assert.equal(mounted,true);
 assert.equal(ctx.requiredItemSpecificsSatisfied(),false,'Required empty row fails before eBay displays an error');
 value='Adapter';assert.equal(ctx.requiredItemSpecificsSatisfied(),true);
 ctx.document.body.innerText='Additional details are required: Type';
 assert.equal(ctx.requiredItemSpecificsSatisfied(),false);
 console.log('specifics visibility tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
