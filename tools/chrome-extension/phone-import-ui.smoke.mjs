import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root=new URL('../../apps/local_dashboard/',import.meta.url);
const browser=await chromium.launch({headless:true,channel:'chrome'});
try{
 const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 const errors=[];let imports=0,payload;
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/products/phone-import'){
   imports++;payload=route.request().postDataJSON();
   return route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify({product_id:9,created:true,message:'Draft saved. Review it before scheduling.'})});
  }
  if(route.request().method()==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type'}});
  if(['/phone-import.html','/phone-import.js'].includes(path))return route.fulfill({contentType:path.endsWith('.js')?'text/javascript':'text/html',body:await readFile(new URL(path.slice(1),root))});
  return route.fulfill({status:404,body:''});
 });
 const link='https://www.homedepot.com/p/Test-Garden-Nozzle/123456789?tracking=phone';
 await page.goto('http://phone.test/phone-import.html?api=http://phone.test:8000&source='+encodeURIComponent(link));
 assert.equal(imports,0,'opening a shared link must never import automatically');
 assert.equal(await page.locator('#source-url').inputValue(),link);
 await page.locator('#submit').click();
 await page.waitForFunction(()=>document.querySelector('#result').textContent.includes('Product #9'));
 assert.equal(imports,1);assert.equal(payload.source_url,link);
 await page.locator('#source-url').fill('https://evil.example/p/Test/123456789');
 await page.locator('#submit').click();assert.equal(imports,1);
 assert.ok((await page.locator('#result').textContent()).includes('full Home Depot'));
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
 assert.deepEqual(errors,[]);
 console.log('PASS iPhone-sized form: shared-link prefill, explicit import, invalid URL rejection and viewport fit');
}finally{await browser.close()}
