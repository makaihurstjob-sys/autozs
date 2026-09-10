const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(`${__dirname}/background.js`,'utf8');
const worker=source.slice(source.indexOf('let supplierReceiptRunning'),source.indexOf('let profitReconciliationRunning'));
async function check(wrongOrder=false, withCharge=false){
 const writes=[],closed=[];
 const context={URL,setTimeout:fn=>fn(),canRunAutozsWorkerJobs:async()=>true,
 localApiJson:async(path,options)=>{if(path.endsWith('/next'))return {supplier_order_id:4,external_order_id:'WK37553521',url:'https://www.homedepot.com/myaccount/order-details?orderNumber=WK37553521'};writes.push(JSON.parse(options.body));},
 chrome:{tabs:{create:async()=>({id:42}),remove:async id=>closed.push(id)},scripting:{executeScript:async({func,args})=>{
 context.location={href:'https://www.homedepot.com/myaccount/order-details?orderNumber=WK37553521'};
 context.document={querySelectorAll:()=>[],body:{innerText:`ORDER # ${wrongOrder?'WK00000000':'WK37553521'} Subtotal:\n$4.88\nDelivery:\nFREE\nSales Tax:\n$0.40\nTotal:\n$5.28\nView Charge History`}};
 if(withCharge){context.document.querySelector=()=>null;context.document.querySelectorAll=()=>[{textContent:"View Charge History",click:()=>{context.document.body.innerText+="\nCharge History\nCHARGE\nAdjusted Total\n$5.28";}}];} context.args=args;return [{result:await vm.runInContext(`(${func.toString()})(...args)`,context)}];}}}};
 vm.createContext(context);await vm.runInContext(worker+'\nreconcileNextSupplierReceipt()',context);
 if(withCharge)assert.equal(writes[0].charge_history_text,"Charge History\nCHARGE\nAdjusted Total\n$5.28"); assert.deepEqual(closed,[42]);assert.equal(writes.length,1);
 if(wrongOrder)assert.match(writes[0].error,/could not be verified/);
 else {assert.equal(writes[0].external_order_id,'WK37553521');assert.equal(writes[0].financial_text,'Subtotal:\n$4.88\nDelivery:\nFREE\nSales Tax:\n$0.40\nTotal:\n$5.28');}
}
(async()=>{await check();await check(true);await check(false,true);console.log('Supplier receipt capture, wrong-order rejection and cleanup passed');})().catch(error=>{console.error(error);process.exitCode=1;});
