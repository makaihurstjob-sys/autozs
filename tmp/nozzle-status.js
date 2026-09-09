(async()=>{const s=await localApiJson('/supplier-orders/4');return {status:s.status,reason:s.failure_reason};})()
