import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const root=new URL('../../apps/local_dashboard/',import.meta.url);
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
for(const [width,height] of [[320,568],[390,664],[390,844],[430,932]]){
 const page=await browser.newPage({viewport:{width,height},isMobile:true,hasTouch:true});const errors=[];const decisions=[];let approved=7;let fail=false;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async r=>{const u=new URL(r.request().url());const path=u.pathname;
 if(path.endsWith('.html')||path.endsWith('.css')||path.endsWith('.js'))return r.fulfill({contentType:path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'text/html',body:await readFile(new URL(path.slice(1),root))});
 if(path==='/depop/photo-queue')return r.fulfill({json:[{product_id:300,product_title:'Test bag',pending:2},{product_id:301,product_title:'Second bag',pending:0}]});
 if(path==='/depop/photo-review/301')return r.fulfill({json:{product_id:301,variants:[{id:2,color:'Red',variant_key:'red',depop_listing_id:'posted'},{id:3,color:'Blue',variant_key:'blue'},{id:4,color:'Green',variant_key:'green'}],photos:[2,3,4].flatMap(id=>Array.from({length:4},(_,i)=>({id:id*100+i,variant_id:id,status:'approved'})))}});
 if(path==='/depop/jobs')return r.fulfill({json:[{variant_id:1,status:'queued',attempts:0},{variant_id:3,status:'cancelled',attempts:1},{variant_id:4,status:'cancelled',attempts:0}]});
 if(path==='/depop/photo-review/300')return r.fulfill({json:{product_id:300,product_title:'Test bag',variants:[{id:1,color:'Black',variant_key:'black'},...Array.from({length:7},(_,i)=>({id:20+i,color:'Color '+i,variant_key:'color-'+i}))],photos:[...Array.from({length:8},(_,i)=>({id:500+i,kind:'variation',variant_id:i===0?1:19+i,image_url:'/bag.svg'})),...Array.from({length:approved},(_,i)=>({id:100+i,kind:'review',status:'approved',variant_id:1,sort_order:i,image_url:'/bag.svg'})),{id:10,kind:'review',status:'pending',variant_id:1,image_url:'/bag.svg',crop_zoom:1},{id:11,kind:'review',status:'pending',variant_id:1,image_url:'/bag.svg'}]}});
 if(path.endsWith('/decision')){const d=r.request().postDataJSON();decisions.push(d);if(fail)return r.fulfill({status:500,json:{detail:'test failure'}});if(d.status==='approved')approved++;if(d.status==='pending')approved--;return r.fulfill({json:{}})}
 if(path==='/bag.svg')return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="800"><rect width="500" height="800" fill="gray"/></svg>'});
 return r.fulfill({json:[]});});
 await page.goto('http://mobile.test/mobile.html?api=http://mobile.test');
 await page.evaluate(()=>{applyMarketplace('depop');setView('chat')});
 await page.evaluate(()=>refreshDepop(new AbortController().signal));
 assert.equal(await page.locator('#drafts-label').innerText(),'Approved');
 assert.equal(await page.locator('#drafts-count').innerText(),'1/84');
 assert.equal(await page.locator('#approved-week-note').innerText(),'83 more for a week');
 await page.evaluate(()=>updateApprovedWeek(84));
 assert.equal(await page.locator('#approved-week-note').innerText(),'Full week ready');
 await page.evaluate(()=>updateApprovedWeek(null));
 assert.equal(await page.locator('#drafts-count').innerText(),'-/84');
 await page.evaluate(()=>refreshDepop(new AbortController().signal));
 const frame=page.locator('#depop-review');
 await frame.locator('#picker .queue-row').first().click();
 assert.equal(await page.locator('iframe').count(),0);
 await frame.locator('#deck .card').last().waitFor();
 await frame.locator('.chip').first().click();
 await page.waitForFunction(()=>document.querySelector('#photo-readiness')?.textContent.includes('photo-ready listing'));
 assert.match(await frame.locator('#photo-readiness').innerText(), /1 photo-ready listing.*All Depop products.*Black: 3\/4/);
 if(process.env.SCREENSHOT_OUT&&width===390&&height===844)await page.screenshot({path:process.env.SCREENSHOT_OUT+'-review.png'});const box=await frame.locator('#deck').boundingBox();assert.ok(Math.abs(box.width-box.height)<1,'square preview');
 const yes=await frame.locator('#btn-yes').boundingBox();assert.ok(yes.y+yes.height<height-60,'approve visible above navigation');
 await frame.locator('#variants .chip').first().click();
 assert.equal(await frame.locator('.color-dialog').count(),0);
 assert.equal(await frame.locator('#variants .chip img').first().isVisible(),true);
 await page.waitForFunction(()=>document.querySelector('#variants .chip img')?.naturalWidth>0);
 await frame.locator('#variants .chip').last().click();
 await frame.locator('#variants .chip').first().click();
 assert.equal(await frame.locator('#all-colors').isVisible(),false);
 await frame.locator('#crop-toggle').click();await frame.locator('#crop-zoom').fill('2');await frame.locator('#crop-cancel').click();
 await frame.locator('#square-crop').click();await frame.locator('#crop-toggle').click();await frame.locator('#crop-zoom').fill('1.5');await frame.locator('#crop-save').click();
 await frame.locator('.chip').first().click();await frame.locator('#btn-yes').click();await page.waitForTimeout(400);
 await page.waitForFunction(()=>document.querySelector('#photo-readiness')?.textContent.includes('photo-ready listing'));
 assert.match(await frame.locator('#photo-readiness').innerText(), /2 photo-ready listings.*Black: 0\/4/);
 assert.equal(await page.locator('#drafts-count').innerText(),'2/84');
 await frame.locator('#undo').click();await page.waitForTimeout(350);
 await page.waitForFunction(()=>document.querySelector('#photo-readiness')?.textContent.includes('photo-ready listing'));
 assert.match(await frame.locator('#photo-readiness').innerText(), /1 photo-ready listing.*All Depop products.*Black: 3\/4/);
 fail=true;await frame.locator('#btn-yes').click();await page.waitForTimeout(350);
 await page.waitForFunction(()=>document.querySelector('#photo-readiness')?.textContent.includes('photo-ready listing'));
 assert.match(await frame.locator('#photo-readiness').innerText(), /1 photo-ready listing/);
 assert.equal(decisions[0].background_mode,'crop');assert.equal(decisions[0].crop_zoom,1.5);assert.equal(decisions[0].variant_id,1);
 await frame.locator('#review-products').click();await frame.locator('#picker .queue-row').first().waitFor();
 await page.waitForFunction(()=>document.querySelector('#photo-readiness')?.textContent.includes('photo-ready listing'));
 assert.match(await frame.locator('#photo-readiness').innerText(), /1 photo-ready listing/);
 await page.evaluate(()=>applyMarketplace('ebay'));
 assert.equal(await page.locator('#drafts-label').innerText(),'Drafts');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);assert.deepEqual(errors,[]);
 console.log(`PASS ${width}x${height}: counter approval/undo/failure/reserved batch, square, visible actions, crop persistence, no overflow/errors`);await page.close();
}
}finally{await browser.close()}

