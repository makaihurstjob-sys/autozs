import fs from 'node:fs';
const ids=[278,288,285,290,303,299,297,305,306,311,313];
const until=Date.now()+55_000;
let previous='';
async function evidence(){
 const tabs=await(await fetch('http://127.0.0.1:9225/json/list')).json();
 const tab=tabs.find(t=>t.type==='page'&&t.url.includes('ebay.com/lstng'));
 if(!tab)return;
 const ws=new WebSocket(tab.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 return await new Promise(resolve=>{
  const timer=setTimeout(()=>{ws.close();resolve();},4000);
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id!==1)return;clearTimeout(timer);ws.close();
   const value=m.result?.result?.value;
   if(value){fs.writeFileSync('tmp/fixed-batch-browser-latest.json',JSON.stringify(value,null,2));
    if(value.confirmation){fs.writeFileSync(`tmp/confirmed-${value.itemId}.json`,JSON.stringify(value,null,2));}}
   resolve(value);
  };
  ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{returnByValue:true,expression:`(()=>{const text=document.body.innerText;const confirmation=/Your listing has been (scheduled|listed|revised)/i.test(text);return {at:new Date().toISOString(),url:location.href,title:document.title,confirmation,itemId:confirmation?(text.match(/ID-?([0-9]{12})/)||[])[1]:null,brand:document.querySelector('button[name="attributes.Brand"]')?.innerText,type:document.querySelector('button[name="attributes.Type"]')?.innerText,text:confirmation?text:text.slice(0,2200)};})()`}}));
 });
}
while(Date.now()<until){
 const jobs=await Promise.all(ids.map(async id=>await(await fetch(`http://127.0.0.1:8000/listing-jobs/${id}`)).json()));
 const summary=jobs.map(j=>({id:j.id,product:j.product_id,status:j.status,message:j.message}));
 fs.writeFileSync('tmp/fixed-batch-progress.json',JSON.stringify({at:new Date().toISOString(),jobs:summary},null,2));
 const state=jobs.map(j=>`${j.id}:${j.status}`).join(' ');
 if(state!==previous){console.log(state);previous=state;}
 await evidence();
 if(jobs.every(j=>['completed','needs_review','failed','cancelled','tombstoned'].includes(j.status)))break;
 await new Promise(r=>setTimeout(r,8000));
}

