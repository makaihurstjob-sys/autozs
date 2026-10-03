const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/background.js`, 'utf8');
let calls = 0, mime = 'image/jpeg', size = 3;
const context = {LOCAL_API:'https://api.test', Uint8Array, AbortSignal, bytesToBase64:b=>Buffer.from(b).toString('base64'), fetch:async()=>{calls++;return {ok:true,headers:{get:()=>mime},arrayBuffer:async()=>new Uint8Array(size).buffer}}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('async function readDepopImage(')), context);
(async()=>{
  for (const path of ['../secret', 'https://evil.test/x.jpg', 'downloads/product_images/1/../../x.jpg']) await assert.rejects(context.readDepopImage(path));
  assert.equal(calls,0);
  const result = await context.readDepopImage('downloads/product_images/288/depop-9.jpg'); assert.equal(result.base64,'AAAA');
  mime='text/html'; await assert.rejects(context.readDepopImage('downloads/product_images/288/depop-9.jpg'));
  mime='image/jpeg'; size=0; await assert.rejects(context.readDepopImage('downloads/product_images/288/depop-9.jpg'));
  console.log('Depop image transfer tests passed');
})().catch(e=>{console.error(e);process.exitCode=1});
