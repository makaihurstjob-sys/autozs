(async()=>{const s=await localApiJson('/supplier-orders/4');return {status:s.status,tracking:s.tracking_number,carrier:s.carrier,workerMode:await readAutozsWorkerMode()};})()
