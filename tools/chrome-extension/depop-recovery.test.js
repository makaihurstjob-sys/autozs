const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/depop-fill.js`, 'utf8');
const functions = source.slice(source.indexOf('  function listingIdentity'), source.indexOf('  async function armPublicationConfirmation'))
  + source.slice(source.indexOf('  async function resumePublicationConfirmation'), source.indexOf('  function metricNumber'));
async function main() {
  let now = Date.now(), hydrated = false, fail = true, pending, acknowledgements = 0, waits = 0;
  const token = 'origin-tab';
  const original = { jobId:'7', tabToken:token, username:'m4coq', title:'Bag', price:30, postClickedAt:new Date(now).toISOString() };
  pending = structuredClone(original);
  const context = { URL, Number, Date: class extends Date { static now() { return now; } }, PENDING_PUBLICATION_KEY:'pending',
    location:{ origin:'https://www.depop.com', href:'https://www.depop.com/products/new-bag/' },
    sessionStorage:{ getItem:()=>token, removeItem(){} },
    document:{ referrer:'https://www.depop.com/products/create/',
      querySelectorAll:()=>[{href:'https://www.depop.com/m4coq/likes/'}],
      querySelector:()=>hydrated?{querySelector:(selector)=>selector.includes('name')?{textContent:'Bag'}:{getAttribute:()=> '30'}}:null },
    storageGet:async()=>structuredClone(pending), storageSet:async(key,value)=>{pending=structuredClone(value);},
    storageRemove:async()=>{pending=null;}, showStatus(){},
    wait:async()=>{waits++;now+=500;hydrated=true;},
    apiRequest:async()=>{acknowledgements++;assert.ok(pending.publicationEvidence,'evidence durable before acknowledgement');if(fail)throw Error('response lost');},
  };
  vm.createContext(context);vm.runInContext(functions,context);
  await assert.rejects(()=>context.resumePublicationConfirmation(), /response lost/);
  assert.equal(waits,1,'hydration was awaited');
  assert.ok(pending.publicationEvidence,'failed acknowledgement preserves observation');
  // Simulate restart well after the original two-minute evidence window.
  now+=600000;hydrated=false;fail=false;
  await context.resumePublicationConfirmation();
  assert.equal(pending,null,'acknowledged publication releases next-job guard');
  assert.equal(acknowledgements,2);
  pending=structuredClone(original);acknowledgements=0;
  await context.resumePublicationConfirmation();
  assert.equal(acknowledgements,0,'old unknown outcome never invents success');
  assert.ok(pending,'unknown outcome remains held');
  pending={...original,publicationEvidence:{id:'new-bag',url:'https://evil.example/products/new-bag/',observedAt:new Date(now).toISOString()}};
  await context.resumePublicationConfirmation();assert.equal(acknowledgements,0,'untrusted evidence rejected');
  pending={...original,tabToken:'other-tab'};const before=waits;
  await context.resumePublicationConfirmation();assert.equal(waits,before,'other tabs cannot reconcile');
  now=Date.parse(original.postClickedAt);
  pending=structuredClone(original);
  context.location.href='https://www.depop.com/products/create/success/?productId=938270465';
  let links=[{textContent:'View listing',href:'https://www.depop.com/products/new-bag/manage/'}];
  context.document.querySelector=()=>({textContent:"Nice! It's listed",querySelectorAll:()=>links});
  let destination=null;
  context.location.assign=url=>{destination=url;};
  await context.watchForPublishedDestination(pending);
  assert.equal(destination,'https://www.depop.com/products/new-bag/');
  assert.equal(acknowledgements,0,'success screen alone cannot acknowledge publication');
  links.push(links[0]);assert.equal(context.successListingDestination(pending),null,'ambiguous links rejected');
  links=[{textContent:'View listing',href:'https://evil.example/products/new-bag/'}];
  assert.equal(context.successListingDestination(pending),null,'foreign destination rejected');
  links=[{textContent:'View listing',href:'https://www.depop.com/products/new-bag/'}];
  assert.equal(context.successListingDestination({...pending,tabToken:'other'}),null,'tab guard retained');
  now+=120001;assert.equal(context.successListingDestination(pending),null,'stale success rejected');
  now=Date.parse(original.postClickedAt);
  context.location.href='https://www.depop.com/products/new-bag/';
  context.document.referrer='https://www.depop.com/products/create/success/?productId=938270465';
  context.document.querySelector=()=>({querySelector:selector=>selector.includes('name')?{textContent:'Bag'}:{getAttribute:()=> '30'}});
  assert.equal(context.findPublishedListing(pending,true)?.id,'new-bag','success-to-product recovery verifies schema');
  pending.price=31;assert.equal(context.findPublishedListing(pending,true),null,'wrong price held');
  pending=structuredClone(original);
  context.document.querySelector=()=>null;
  let data={ '@type':'Product', name:'Truncated...', description:'Bag\n\nFull description',
    offers:{'@type':'Offer',url:'https://www.depop.com/products/new-bag/manage/',priceCurrency:'USD',price:'30.00'} };
  let scripts=[{textContent:JSON.stringify(data)}];
  context.document.querySelectorAll=selector=>selector.includes('script')?scripts:[{href:'https://www.depop.com/m4coq/likes/'}];
  const verify=()=>context.findPublishedListing(pending,true);
  assert.equal(verify()?.id,'new-bag','current JSON-LD layout verifies full title and price');
  for (const [label, mutate] of [
    ['wrong title', d=>d.description='Other bag\n\nFull description'],
    ['wrong price', d=>d.offers.price='31'],
    ['wrong currency', d=>d.offers.priceCurrency='GBP'],
    ['unrelated listing', d=>d.offers.url='https://www.depop.com/products/other-bag/'],
    ['foreign listing', d=>d.offers.url='https://evil.example/products/new-bag/'],
    ['wrong schema', d=>d['@type']='Article'],
    ['ambiguous offers', d=>d.offers=[d.offers]],
  ]) {
    const changed=structuredClone(data);mutate(changed);scripts=[{textContent:JSON.stringify(changed)}];
    assert.equal(verify(),null,`${label} held`);
  }
  scripts=[{textContent:'{invalid'}];assert.equal(verify(),null,'malformed JSON held');
  scripts=[{textContent:JSON.stringify(data)},{textContent:JSON.stringify(data)}];assert.equal(verify(),null,'ambiguous products held');
  scripts=[{textContent:JSON.stringify(data)}];
  context.document.querySelectorAll=selector=>selector.includes('script')?scripts:[{href:'https://www.depop.com/other/likes/'}];
  assert.equal(verify(),null,'wrong signed-in account held');
  context.document.querySelectorAll=selector=>selector.includes('script')?scripts:[{href:'https://www.depop.com/m4coq/likes/'}];
  context.document.referrer='https://www.depop.com/sellinghub/';assert.equal(verify(),null,'unrelated navigation held');
  context.document.referrer='https://www.depop.com/products/create/success/?productId=938270465';
  now+=120001;assert.equal(verify(),null,'stale JSON-LD held');
  console.log('Depop recovery tests passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
