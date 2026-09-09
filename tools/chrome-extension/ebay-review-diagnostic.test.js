const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/ebay-fill.js`, 'utf8');
function extract(name) {
  let start = source.indexOf('function ' + name + '(');
  if (source.slice(start - 6, start) === 'async ') start -= 6;
  return source.slice(start, source.indexOf('\n}', start) + 2);
}

{
  // A stale, empty listingFillReviewLabels snapshot (from the fill pass
  // before repairs and the final submit click) used to make this function
  // report no cause at all, even when eBay's click-time validation just
  // rejected a field a fresh check would still catch right now.
  const ctx = {
    listingFillReviewLabels: [],
    criticalListingCheckDetails: () => [
      { label: 'item specifics', ok: false },
      { label: 'condition', ok: true },
    ],
    itemSpecificDiagnostic: () => 'empty required: Genus',
    conditionControls: () => [],
    isVisible: () => true,
    normalizeText: () => '',
    normalizeComparableValue: () => '',
    labelText: () => '',
    nearbyText: () => '',
    ebayItemSpecificRows: () => [],
    ebayItemSpecificRowValue: () => '',
    document: { body: { innerText: '' }, querySelectorAll: () => [] },
  };
  vm.createContext(ctx);
  vm.runInContext(extract('describeUnconfirmedSubmission'), ctx);
  const shown = ctx.describeUnconfirmedSubmission({});
  assert.match(shown, /AUTOZS fill review: item specifics/, 'a freshly failing check must be reported even when the stale fill labels are empty');
  assert.match(shown, /item specifics diagnostic: empty required: Genus/, 'the real failing field must be named, not left blank');
}

{
  // Some categories render the live condition value as a bare button (just
  // "New") with no "condition" wording anywhere on the control or its
  // immediate ancestor, so neither the checked-state nor summary-text
  // heuristics can see it. The heading-scoped fallback should still find it.
  const bareButton = { innerText: 'New', textContent: 'New', getAttribute: () => '' };
  const container = { querySelectorAll: (selector) => (selector.includes('button') ? [bareButton] : []) };
  const heading = { innerText: 'Condition', textContent: 'Condition', closest: () => container };
  const ctx = {
    normalizeText: (v) => String(v || '').toLowerCase().replace(/[^a-z0-9]+/g, ''),
    isVisible: () => true,
    nearbyText: () => '',
    labelText: () => '',
    conditionQueryAll: () => [],
    conditionControls: () => [],
    isEbayListingEditorPage: () => true,
    document: { querySelectorAll: () => [heading] },
  };
  vm.createContext(ctx);
  vm.runInContext(extract('conditionSelectionMatches'), ctx);
  assert.equal(ctx.conditionSelectionMatches('New'), true, 'a bare "New" button under a Condition heading should match');
  assert.equal(ctx.conditionSelectionMatches('Used'), false, 'a section that only contains "New" must not match a different condition');
}

console.log('review diagnostic and condition heading fallback tests passed');
