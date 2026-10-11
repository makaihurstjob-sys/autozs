import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const root=new URL('../../apps/local_dashboard/',import.meta.url);
const baseline=execFileSync('git',['show','569ce8b:apps/local_dashboard/photo-review.js'],{encoding:'utf8'});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
for(const version of ['before','after']) {
 const times=[];
 for(let run=0;run<3;run++) {
 const page=await browser.newPage({viewport:{width:390,height:844}});
 await page.route('**/*',async route=>{
 const path=new URL(route.request().url()).pathname;
 if(/\.(html|css|js)$/.test(path))return route.fulfill({contentType:path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'text/html',body:version==='before'&&path==='/photo-review.js'?baseline:await readFile(new URL(path.slice(1),root))});
 if(path==='/depop/photo-queue'){await sleep(200);return route.fulfill({json:Array.from({length:19},(_,i)=>({product_id:300+i,pending:1}))});}
 if(path==='/depop/jobs'){await sleep(400);return route.fulfill({json:[]});}
 if(path.startsWith('/depop/photo-review/')){await sleep(path.endsWith('/300')?100:250);return route.fulfill({json:{product_id:Number(path.split('/').at(-1)),product_title:'Speed test',variants:[{id:1,color:'Black',variant_key:'black'}],photos:[{id:10,kind:'review',variant_id:1,status:'pending',image_url:'/photo.svg'}]}});}
 if(path==='/photo.svg'){await sleep(150);return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600"><rect width="600" height="600" fill="gray"/></svg>'});}
 return route.fulfill({json:[]});
 });
 await page.goto('http://speed.test/mobile.html?api=http://speed.test');
 const start=performance.now();
 await page.evaluate(()=>{applyMarketplace('depop');setView('chat');openDepopReview(300)});
 await page.waitForFunction(()=>{const img=document.querySelector('#depop-review #deck .card:last-child img.photo');return img?.complete&&img.naturalWidth>0});
 times.push(Math.round(performance.now()-start));
 // Readiness must still finish correctly after first-photo rendering.
 await page.waitForFunction(()=>document.querySelector('#photo-readiness')?.textContent.includes('photo-ready listing'));
 await page.close();
 }
 const median=[...times].sort((a,b)=>a-b)[1];console.log(JSON.stringify({version,catalogProducts:19,simulatedApiMs:'100 current / 250 other / 400 jobs',simulatedImageMs:150,firstPhotoMs:times,medianMs:median}));
 if(version==='after')assert.ok(median<700,'first photo must not wait for the full catalog');
}
} finally {await browser.close()}
