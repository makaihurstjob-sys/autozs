const target = '7E8D2BD407B06AF3781F7F2BCA00230E';
const tabs = await (await fetch('http://127.0.0.1:9225/json/list')).json();
const tab = tabs.find(t=>t.id === target);
if (!tab) throw Error('Target missing');
const ws = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
ws.send(JSON.stringify({id:1,method:'Page.reload',params:{}}));
setTimeout(()=>{ws.close();console.log('reload sent');},500);
