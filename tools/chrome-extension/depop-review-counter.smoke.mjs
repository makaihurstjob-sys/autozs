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
 if(path==='/depop/jobs')return r.fulfill({json:[{variant_id:1,status:'queued',attempts:0}]});
 if(path==='/depop/photo-review/300')return r.fulfill({json:{product_title:'Test bag',variants:[{id:1,color:'Black',variant_key:'black'}],photos:[...Array.from({length:approved},(_,i)=>({id:100+i,kind:'review',status:'approved',variant_id:1,sort_order:i,image_url:'/bag.svg'})),{id:10,kind:'review',status:'pending',variant_id:1,image_url:'/bag.svg',crop_zoom:1},{id:11,kind:'review',status:'pending',variant_id:1,image_url:'/bag.svg'}]}});
 if(path.endsWith('/decision')){const d=r.request().postDataJSON();decisions.push(d);if(fail)return r.fulfill({status:500,json:{detail:'test failure'}});if(d.status==='approved')approved++;if(d.status==='pending')approved--;return r.fulfill({json:{}})}
 if(path==='/bag.svg')return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="800"><rect width="500" height="800" fill="gray"/></svg>'});
 return r.fulfill({json:[]});});
 await page.goto('http://mobile.test/mobile.html?api=http://mobile.test');
 await page.evaluate(()=>{applyMarketplace('depop');setView('chat')});
 const frame=page.frameLocator('#photo-review-frame');
 await frame.locator('#picker').waitFor({state:'visible'}).catch(()=>{});
 // Exercise actual embedded review workflow with disposable responses.
 await page.locator('#photo-review-frame').evaluate(f=>f.src='http://mobile.test/photos.html?embedded=1&product_id=300&api=http://mobile.test');
 await frame.locator('#deck .card').last().waitFor();
 await frame.locator('.chip').first().click();
 assert.match(await frame.locator('#photo-readiness').innerText(), /0 photo-ready listings.*Black: 3\/4/);
 if(process.env.SCREENSHOT_OUT&&width===390&&height===844)await page.screenshot({path:process.env.SCREENSHOT_OUT+'-review.png'});const box=await frame.locator('#deck').boundingBox();assert.ok(Math.abs(box.width-box.height)<1,'square preview');
 const yes=await frame.locator('#btn-yes').boundingBox();assert.ok(yes.y+yes.height<height-60,'approve visible above navigation');
 await frame.locator('#all-colors').click();await frame.locator('.color-dialog .chip').first().click();await frame.locator('#color-done').click();
 await frame.locator('#crop-toggle').click();await frame.locator('#crop-zoom').fill('2');await frame.locator('#crop-cancel').click();
 await frame.locator('#square-crop').click();await frame.locator('#crop-toggle').click();await frame.locator('#crop-zoom').fill('1.5');await frame.locator('#crop-save').click();
 await frame.locator('.chip').first().click();await frame.locator('#btn-yes').click();await page.waitForTimeout(400);
 assert.match(await frame.locator('#photo-readiness').innerText(), /1 photo-ready listing.*Black: 0\/4/);
 await frame.locator('#undo').click();await page.waitForTimeout(350);
 assert.match(await frame.locator('#photo-readiness').innerText(), /0 photo-ready listings.*Black: 3\/4/);
 fail=true;await frame.locator('#btn-yes').click();await page.waitForTimeout(350);
 assert.match(await frame.locator('#photo-readiness').innerText(), /0 photo-ready listings/);
 assert.equal(decisions[0].background_mode,'crop');assert.equal(decisions[0].crop_zoom,1.5);assert.equal(decisions[0].variant_id,1);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);assert.deepEqual(errors,[]);
 console.log(`PASS ${width}x${height}: counter approval/undo/failure/reserved batch, square, visible actions, crop persistence, no overflow/errors`);await page.close();
}
}finally{await browser.close()}

