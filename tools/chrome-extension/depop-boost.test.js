const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/depop-fill.js`, 'utf8');
async function main() {
  for (const scenario of ['off', 'on', 'missing', 'duplicate', 'disabled', 'indeterminate', 'stuck', 'rerender', 'disconnected', 'wrong-rate', 'missing-rate', 'ambiguous-rate']) {
    let clicks = 0;
    let control = {checked: !['off', 'stuck', 'rerender'].includes(scenario), isConnected: scenario !== 'disconnected',
      disabled: scenario === 'disabled', indeterminate: scenario === 'indeterminate',
      click() { clicks++; if (scenario !== 'stuck') this.checked = true; }};
    const heading = {textContent: 'Boost your listing', parentElement: {textContent: scenario === 'wrong-rate' ? 'Pay 15%' : scenario === 'missing-rate' ? 'Boost' : scenario === 'ambiguous-rate' ? '12% 15%' : 'Pay an extra 12% fee, only if you sell.',
      querySelectorAll: () => scenario === 'missing' ? [] : scenario === 'duplicate' ? [control, control] : [control]}};
    const context = {document: {querySelectorAll: () => [heading]},
      wait: async () => {if (scenario === 'rerender') control = {...control, checked: false};}};
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('  function boostControl'), source.indexOf('  async function armPublicationConfirmation')), context);
    assert.equal(await context.enableBoosting(), ['off', 'on'].includes(scenario), scenario);
    if (['on', 'missing', 'duplicate', 'disabled', 'indeterminate', 'wrong-rate', 'missing-rate', 'ambiguous-rate'].includes(scenario)) assert.equal(clicks, 0, scenario);
  }
  console.log('Depop 12% boost default tests passed (12 scenarios).');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
