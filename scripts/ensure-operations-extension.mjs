// The browser process being alive does not prove its extension can receive
// events. Probe the existing worker, including normal dormant workers, through
// a background extension page. Never reload while any job owns live work.
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

export async function recoverOperationsExtension({ probe, idle, reload, expectedId }) {
  let health = await probe();
  const valid = value => value?.id === expectedId && value?.name === 'AutoZS Source Capture';
  if (!valid(health)) throw new Error('Operations extension identity could not be verified');
  if (health.response?.ok) return { status: 'healthy', mode: health.response.mode };
  if (!(await idle())) return { status: 'deferred', reason: 'AUTOZS jobs are active' };
  const loadedId = await reload();
  if (loadedId !== expectedId) throw new Error('Reloaded extension identity mismatch');
  health = await probe();
  if (!valid(health) || health.response?.ok !== true) throw new Error('Operations extension failed its post-recovery check');
  return { status: 'recovered', mode: health.response.mode };
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 0;
    this.pending = new Map();
    ws.onmessage = event => {
      const message = JSON.parse(event.data);
      const request = this.pending.get(message.id);
      if (!request) return;
      this.pending.delete(message.id);
      clearTimeout(request.timer);
      message.error ? request.reject(new Error(message.error.message)) : request.resolve(message.result);
    };
  }
  call(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP ${method} timed out`));
      }, 12000);
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }
  close() {
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.reject(new Error('CDP closed'));
    }
    this.pending.clear();
    this.ws.close();
  }
}

async function main() {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const extensionPath = path.join(root, 'tools', 'chrome-extension');
  const expectedId = [...createHash('sha256').update(extensionPath, 'utf16le').digest().subarray(0, 16)]
    .map(byte => String.fromCharCode(97 + (byte >> 4), 97 + (byte & 15))).join('');
  const version = await (await fetch('http://127.0.0.1:9225/json/version', { signal: AbortSignal.timeout(5000) })).json();
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Operations browser connection timed out')), 5000);
    ws.onopen = () => { clearTimeout(timer); resolve(); };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('Operations browser connection failed')); };
  });
  const cdp = new Cdp(ws);
  try {
    const probe = async () => {
      const { targetId } = await cdp.call('Target.createTarget', {
        url: `chrome-extension://${expectedId}/popup.html`, background: true,
      });
      try {
        const { sessionId } = await cdp.call('Target.attachToTarget', { targetId, flatten: true });
        const expression = `new Promise(resolve => {
          const timer = setTimeout(() => resolve({id:globalThis.chrome?.runtime?.id,name:globalThis.chrome?.runtime?.getManifest?.().name,error:'Worker response timed out'}),7000);
          const check = () => {
            if (!globalThis.chrome?.runtime?.id) { setTimeout(check,100); return; }
            chrome.runtime.sendMessage({type:'autozs-worker-mode'},response => {
              clearTimeout(timer);
              resolve({id:chrome.runtime.id,name:chrome.runtime.getManifest().name,response,error:chrome.runtime.lastError?.message||null});
            });
          };
          check();
        })`;
        let result;
        for (let attempt = 0; attempt < 3; attempt++) {
          try {
            result = await cdp.call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
            break;
          } catch (error) {
            if (attempt === 2 || !/context.*destroyed|Cannot find context/i.test(error.message)) throw error;
          }
        }
        if (result.exceptionDetails) throw new Error('Operations extension health probe failed');
        return result.result?.value;
      } finally {
        await cdp.call('Target.closeTarget', { targetId });
      }
    };
    const result = await recoverOperationsExtension({
      expectedId, probe,
      idle: async () => {
        const check = spawnSync('C:\\AutoZS\\venv\\Scripts\\python.exe', [path.join(root, 'scripts', 'check-operations-idle.py')], {
          encoding: 'utf8', windowsHide: true, timeout: 15000,
        });
        if (check.error || ![0, 1].includes(check.status)) throw new Error('AUTOZS idle check failed');
        return check.status === 0 && JSON.parse(check.stdout).idle === true;
      },
      reload: async () => (await cdp.call('Extensions.loadUnpacked', { path: extensionPath })).id,
    });
    console.log(JSON.stringify(result));
  } finally {
    cdp.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
