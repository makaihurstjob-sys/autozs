import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recoverOperationsExtension } from './ensure-operations-extension.mjs';

const identity = { id: 'expected', name: 'AutoZS Source Capture' };
const healthy = { ...identity, response: { ok: true, mode: 'operations' } };

test('a dormant worker that answers its wake message never reloads', async () => {
  const result = await recoverOperationsExtension({ expectedId: 'expected', probe: async () => healthy,
    idle: async () => { throw Error('should not check'); }, reload: async () => { throw Error('should not reload'); } });
  assert.equal(result.status, 'healthy');
});
test('a configured viewer is preserved', async () => {
  const result = await recoverOperationsExtension({ expectedId: 'expected', probe: async () => ({ ...healthy, response: { ok: true, mode: 'viewer' } }),
    reload: async () => { throw Error('must not reconfigure'); } });
  assert.equal(result.mode, 'viewer');
});
test('a broken worker reloads exactly once, only when idle, and must pass again', async () => {
  let probes = 0, reloads = 0;
  const result = await recoverOperationsExtension({ expectedId: 'expected',
    probe: async () => ++probes === 1 ? { ...identity, error: 'Receiving end does not exist' } : healthy,
    idle: async () => true, reload: async () => { reloads++; return 'expected'; } });
  assert.equal(result.status, 'recovered');
  assert.equal(probes, 2);
  assert.equal(reloads, 1);
});
test('active or uncertain submissions prevent reload', async () => {
  const result = await recoverOperationsExtension({ expectedId: 'expected', probe: async () => identity,
    idle: async () => false, reload: async () => { throw Error('must not reload'); } });
  assert.equal(result.status, 'deferred');
});
test('identity and failed post-recovery checks fail closed', async () => {
  await assert.rejects(recoverOperationsExtension({ expectedId: 'expected', probe: async () => ({ ...healthy, id: 'other' }) }), /identity/);
  await assert.rejects(recoverOperationsExtension({ expectedId: 'expected', probe: async () => identity,
    idle: async () => true, reload: async () => 'other' }), /identity/);
  await assert.rejects(recoverOperationsExtension({ expectedId: 'expected', probe: async () => identity,
    idle: async () => true, reload: async () => 'expected' }), /post-recovery/);
});
