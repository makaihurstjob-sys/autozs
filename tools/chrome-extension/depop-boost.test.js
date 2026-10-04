const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/depop-fill.js`, 'utf8');
async function main() {
  for (const scenario of ['off', 'on', 'missing', 'duplicate', 'disabled', 'indeterminate', 'stuck', 'rerender', 'disconnected']) {
    let clicks = 0;
    let control = {checked: !['off'].includes(scenario), isConnected: scenario !== 'disconnected',
      disabled: scenario === 'disabled', indeterminate: scenario === 'indeterminate',
      click() { clicks++; if (scenario !== 'stuck') this.checked = false; }};
    const heading = {textContent: 'Boost your listing', parentElement: {
      querySelectorAll: () => scenario === 'missing' ? [] : scenario === 'duplicate' ? [control, control] : [control]}};
    const context = {document: {querySelectorAll: () => [heading]},
      wait: async () => {if (scenario === 'rerender') control = {...control, checked: true};}};
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('  function boostControl'), source.indexOf('  async function armPublicationConfirmation')), context);
    assert.equal(await context.disableBoosting(), ['off', 'on'].includes(scenario), scenario);
    if (['off', 'missing', 'duplicate', 'disabled', 'indeterminate'].includes(scenario)) assert.equal(clicks, 0, scenario);
  }
  console.log('Depop boost prevention tests passed (9 scenarios).');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
