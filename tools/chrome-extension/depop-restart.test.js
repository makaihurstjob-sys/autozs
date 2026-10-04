const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/background.js`, 'utf8');
async function main() {
  const persisted = new Map(), created = [], cleared = [];
  let backup = false;
  const context = {
    AUTOZS_ALARM_SCHEDULE: [['depop',1,1],['capture',0.1,0.5]],
    BACKUP_ALLOWED_ALARMS: new Set(['capture']),
    isBackupCaptureExtension:()=>backup,
    chrome:{alarms:{get:async name=>persisted.get(name),
      create:async(name,config)=>{created.push(name);persisted.set(name,{...config,scheduledTime:123456});},
      clear:async name=>{cleared.push(name);persisted.delete(name);}}},
  };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('async function configureAutozsAlarms()'),source.indexOf('\nif (chrome.alarms)')),context);
  await context.configureAutozsAlarms();
  assert.equal(created.length,2);
  // New worker context retains Chrome alarm state, never resets its deadline.
  vm.createContext({...context});
  await context.configureAutozsAlarms();
  assert.equal(created.length,2,'worker wake preserves alarm deadlines');
  persisted.delete('depop');
  await context.configureAutozsAlarms();
  assert.equal(created.length,3,'missing alarm repaired after browser restart');
  persisted.set('depop',{periodInMinutes:10,scheduledTime:999});
  await context.configureAutozsAlarms();
  assert.equal(created.length,4,'changed period repaired');
  backup=true;
  await context.configureAutozsAlarms();
  assert.deepEqual(cleared,['depop'],'backup cannot enable Depop automation');
  console.log('Depop restart alarm tests passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
