import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const root=new URL('../../apps/local_dashboard/',import.meta.url);
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
for(const [width,height] of [[320,568],[390,664],[390,844],[430,932]]){
 const page=await browser.newPage({viewport:{width,height},isMobile:true,hasTouch:true});const errors=[];const decisions=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async r=>{const u=new URL(r.request().url());const path=u.pathname;
 if(path.endsWith('.html')||path.endsWith('.css')||path.endsWith('.js'))return r.fulfill({contentType:path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'text/html',body:await readFile(new URL(path.slice(1),root))});
 if(path==='/depop/photo-review/300')return r.fulfill({json:{product_title:'KKXIU slouchy hobo',variants:[{id:1,color:'Black',variant_key:'black'}],photos:[{id:10,kind:'review',status:'pending',variant_id:1,image_url:'/bag.svg',crop_zoom:1},{id:11,kind:'review',status:'pending',variant_id:1,image_url:'/bag.svg'}]}});
 if(path.endsWith('/decision')){decisions.push(r.request().postDataJSON());return r.fulfill({json:{}})}
 if(path==='/bag.svg')return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="800"><rect width="500" height="800" fill="gray"/></svg>'});
 return r.fulfill({json:[]});});
 await page.goto('http://mobile.test/mobile.html?api=http://mobile.test');
 await page.evaluate(()=>{applyMarketplace('depop');setView('chat')});
 const frame=page.locator('#depop-review');
 await page.evaluate(()=>openDepopReview(300));
 await frame.locator('#deck .card').last().waitFor();
 if(process.env.SCREENSHOT_OUT&&width===390&&height===844)await page.screenshot({path:process.env.SCREENSHOT_OUT+'-review.png'});const box=await frame.locator('#deck').boundingBox();assert.ok(Math.abs(box.width-box.height)<1,'square preview');
 const yes=await frame.locator('#btn-yes').boundingBox();assert.ok(yes.y+yes.height<height-60,'approve visible above navigation');
 await frame.locator('#all-colors').click();await frame.locator('.color-dialog .chip').first().click();await frame.locator('#color-done').click();
 await frame.locator('#crop-toggle').click();await frame.locator('#crop-zoom').fill('2');await frame.locator('#crop-cancel').click();
 await frame.locator('#square-crop').click();await frame.locator('#crop-toggle').click();await frame.locator('#crop-zoom').fill('1.5');await frame.locator('#crop-save').click();
 await frame.locator('.chip').first().click();await frame.locator('#btn-yes').click();await page.waitForTimeout(400);
 assert.equal(decisions[0].background_mode,'crop');assert.equal(decisions[0].crop_zoom,1.5);assert.equal(decisions[0].variant_id,1);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);assert.deepEqual(errors,[]);
 console.log(`PASS ${width}x${height}: square, visible actions, persisted crop and color, no overflow/errors`);await page.close();
}
}finally{await browser.close()}

