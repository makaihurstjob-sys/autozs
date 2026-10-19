const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/depop-fill.js`, 'utf8');
const arm = source.slice(source.indexOf('  async function armPublicationConfirmation'), source.indexOf('  async function resumePublicationConfirmation'));
async function main() {
  for (const failure of ['none', 'storage', 'backend', 'fields', 'boost', 'boost-after-arm']) {
    const handlers = {}, order = [], values = {description:'Purse',priceAmount__input:'30','group-input':'Bags','brand-input':'Other','condition-input':'Brand new','colour-input':'Red','shippingMethods-input':'Large Under 2lb'};
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const context = {jobId:'7',PENDING_PUBLICATION_KEY:'pending',crypto:{randomUUID:()=> 'token'},Date,Number,String,Boolean,
      sessionStorage:{setItem(){}}, chrome:{storage:{local:{}}},storageGet:async()=>null,
      storageSet:async(key,pending)=> {if(pending.postClickedAt){order.push('persist');await gate;if(failure==='storage')throw Error('disk');}},
      apiRequest:async()=> {order.push('backend');if(failure==='backend')throw Error('network');},
      boostingEnabledAtApprovedRate:()=>failure!=='boost' && !(failure==='boost-after-arm' && order.includes('backend')),
      boostRequirementMet:()=>failure!=='boost' && !(failure==='boost-after-arm' && order.includes('backend')),
      depopFieldMatches:(field,value)=>String(values[`${field}-input`]).toLowerCase().replace(/\s+/g, "")===String(value).toLowerCase().replace(/\s+/g, ""),selectionKey:(value)=>String(value||"").toLowerCase().replace(/\s+/g,""),photosReady:()=>true,showStatus:()=>{},watchForPublishedDestination:async()=>true,
      document:{addEventListener:(name,fn)=>handlers[name]=fn,getElementById:(id)=>({value:values[id]})}};
    context.globalThis=context;vm.createContext(context);vm.runInContext(arm,context);
    const ready = await context.armPublicationConfirmation({title:'Purse',price:30,account_key:'m4coq',category:'Bags',brand:'Other',condition:'Brand new',color:'Red',shipping_method:'Large Under 2lb'});
    ready(true,4);
    if(failure==='fields')values['condition-input']='Used';
    const button={innerText:'Post',isConnected:true,disabled:false,click(){order.push('click');handlers.click(event);}};
    let prevented=0;
    const event={type:'click',target:{closest:()=>button},preventDefault(){prevented++;},stopImmediatePropagation(){}};
    handlers.click(event);handlers.click(event);
    assert.equal(prevented,2,'both original clicks synchronously cancelled');
    assert.equal(order.includes('click'),false,'cannot click before durable storage acknowledgement');
    release();await new Promise(resolve=>setImmediate(resolve));
    assert.deepEqual(order,failure==='none'?['persist','backend','click']:failure==='storage'?['persist']:['fields','boost'].includes(failure)?[]:['persist','backend']);
    handlers.click(event);await new Promise(resolve=>setImmediate(resolve));
    assert.equal(order.filter(x=>x==='click').length,failure==='none'?1:0,'uncertainty cannot retry');
  }
  const photoSource=source.slice(source.indexOf('  function photoRegion'),source.indexOf('  async function patchJob'));
  let images=[],busy=false;
  const context={document:{getElementById:()=>({closest:()=>({querySelector:()=>busy?{}:null,querySelectorAll:()=>images})})}};
  vm.createContext(context);vm.runInContext(photoSource,context);
  images=[{complete:true,naturalWidth:100,src:'blob:preview'}];assert.equal(context.photosReady(1),false);
  images=[{complete:true,naturalWidth:100,src:'https://media-photos.depop.com/photo.jpg'}];assert.equal(context.photosReady(1),true);
  busy=true;assert.equal(context.photosReady(1),false);busy=false;
  assert.equal(context.photosReady(2),false);
  const uploadSource = source.slice(source.indexOf('  async function uploadImages'), source.indexOf('  function photoRegion'));
  const uploadContext={document:{getElementById:()=>({})},photoRegion:()=>({querySelectorAll:()=>[{}]}),imageFile:()=>{throw Error('must not fetch');}};
  vm.createContext(uploadContext);vm.runInContext(uploadSource,uploadContext);
  await assert.rejects(()=>uploadContext.uploadImages(['image.jpg']),/Existing draft photos/);
  const trigger = source.slice(source.indexOf('    const scheduler = await storageGet("autozsDepopScheduler")'), source.indexOf('\n  const task =')).replace(/\n  }\s*$/, '');
  for (const settings of [null, {enabled:true,accountKey:'m4coq'}, {enabled:true,autoPublish:true,accountKey:'other'}, {enabled:true,autoPublish:true,accountKey:'m4coq'}]) {
    let clicks=0;
    const context={storageGet:async()=>settings,unresolved:0,photosVerified:true,pkg:{account_key:'m4coq'},visible:()=>true,optionText:()=> 'post',
      document:{querySelectorAll:()=>[{disabled:false,click(){clicks++;}}]}};
    vm.createContext(context);await vm.runInContext(`(async()=>{${trigger}})()`,context);
    assert.equal(clicks,settings?.autoPublish && settings.accountKey==='m4coq'?1:0);
  }
  console.log('Depop submission safety tests passed (6 submission scenarios, 4 photo checks).');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
