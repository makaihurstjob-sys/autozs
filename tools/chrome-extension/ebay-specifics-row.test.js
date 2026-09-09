const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/ebay-fill.js`, 'utf8');
let selected = '', expanded = false, clicks = 0, searched = '';
const option = { getAttribute: () => selected === 'Husky' ? 'true' : 'false', click: () => { selected = 'Husky'; clicks++; } };
const input = {};
const panel = { querySelectorAll: selector => selector.startsWith('input') ? [input] : [option] };
const trigger = {getAttribute: () => expanded ? 'true' : 'false', click: () => { expanded = !expanded; }};
const row = {key:'Brand', valueHost:{querySelectorAll:()=>[trigger]}};
const ctx = {isVisible:()=>true, itemSpecificMatches:(key,value)=>selected===value,
  ebayItemSpecificOptionPanel:()=>expanded ? panel : null,
  waitForCondition:async predicate=>predicate(), delay:async()=>{},
  setEbayTextFieldValue:async (field,value)=>{assert.equal(field,input);searched=value;},
  itemSpecificOptionMatches:(candidate,value)=>candidate===option&&value==='Husky',
  document:{querySelectorAll:()=>{throw Error('Dropdown options must stay inside their panel');}}};
vm.createContext(ctx);
const start=source.indexOf('async function fillEbayItemSpecificRow(');
vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),ctx);
(async()=>{
 assert.equal(await ctx.fillEbayItemSpecificRow(row,'Husky'),true);
 assert.equal(searched,'Husky'); assert.equal(clicks,1); assert.equal(expanded,false);
 assert.equal(await ctx.fillEbayItemSpecificRow(row,'Husky'),true); assert.equal(clicks,1);
 selected=''; option.click=()=>{clicks++;};
 assert.equal(await ctx.fillEbayItemSpecificRow(row,'Husky'),false,'Search text is insufficient without a committed selection');
 console.log('specifics row tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
