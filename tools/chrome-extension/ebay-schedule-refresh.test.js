const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(`${__dirname}/ebay-fill.js`, 'utf8');

function extractFunction(name) {
  let start = source.indexOf('function ' + name + '(');
  if (source.slice(start - 6, start) === 'async ') start -= 6;
  return source.slice(start, source.indexOf('\n}', start) + 2);
}

function extractConstValue(name) {
  const start = source.indexOf('const ' + name + ' ');
  const statement = source.slice(start, source.indexOf(';', start) + 1);
  return vm.runInNewContext(`${statement} ${name}`);
}

function buildContext(overrides = {}) {
  // Setting these as plain properties on the (about-to-be-contextified)
  // object, rather than running the source's own "const" statements through
  // vm.runInContext, keeps them visible both to code executed inside the
  // context (refreshListingScheduleIfStale reads them as bare globals) and
  // to this test's own assertions -- a "const" run via vm.runInContext only
  // lives in the context's internal lexical scope, invisible from outside.
  const ctx = {
    Date,
    Intl,
    LISTING_SCHEDULE_MIN_LEAD_MS: extractConstValue('LISTING_SCHEDULE_MIN_LEAD_MS'),
    LISTING_SCHEDULE_REFRESH_LEAD_MS: extractConstValue('LISTING_SCHEDULE_REFRESH_LEAD_MS'),
    ...overrides,
  };
  vm.createContext(ctx);
  for (const name of ['zoneOffsetMs', 'naiveZonedTimeToDate', 'parseListingSchedule', 'formatAsEasternWallClock', 'refreshListingScheduleIfStale']) {
    vm.runInContext(extractFunction(name), ctx);
  }
  return ctx;
}

(async () => {
  {
    // A known Eastern wall-clock value must resolve to the real UTC instant,
    // not the raw number reinterpreted as some other zone.
    const ctx = buildContext();
    const schedule = ctx.parseListingSchedule('2026-07-01T14:00:00'); // 2pm EDT (UTC-4) in summer
    assert.ok(schedule);
    assert.equal(new Date(schedule.instant).toISOString(), '2026-07-01T18:00:00.000Z');
  }

  {
    // A schedule comfortably in the future must be left untouched -- no pkg
    // mutation, no backend write.
    const updateCalls = [];
    const ctx = buildContext({
      currentWorkflowJobId: () => 'job-1',
      updateListingJob: async (id, payload) => { updateCalls.push([id, payload]); },
    });
    const futureEasternWallClock = ctx.formatAsEasternWallClock(new Date(Date.now() + 3 * 60 * 60 * 1000));
    const pkg = { listing_schedule_at: futureEasternWallClock };
    const schedule = ctx.parseListingSchedule(pkg.listing_schedule_at);
    const result = await ctx.refreshListingScheduleIfStale(pkg, schedule);
    assert.equal(result, schedule, 'an already-safe schedule must be returned unchanged');
    assert.equal(pkg.listing_schedule_at, futureEasternWallClock, 'pkg must not be rewritten when nothing is stale');
    assert.equal(updateCalls.length, 0, 'the backend must not be touched when nothing is stale');
  }

  {
    // A job that has been retried across a long lifecycle (or was requeued
    // hours after its original claim-time roll-forward) can present a
    // schedule that is now in the past, or merely too soon. It must be
    // replaced with a fresh future time, and the backend kept in sync.
    const updateCalls = [];
    const ctx = buildContext({
      currentWorkflowJobId: () => 'job-42',
      updateListingJob: async (id, payload) => { updateCalls.push([id, payload]); },
    });
    const stalePast = ctx.formatAsEasternWallClock(new Date(Date.now() - 60 * 60 * 1000));
    const pkg = { listing_schedule_at: stalePast };
    const schedule = ctx.parseListingSchedule(pkg.listing_schedule_at);
    const result = await ctx.refreshListingScheduleIfStale(pkg, schedule);
    assert.ok(result.instant - Date.now() >= ctx.LISTING_SCHEDULE_MIN_LEAD_MS, 'the refreshed schedule must clear the minimum safe lead');
    assert.notEqual(pkg.listing_schedule_at, stalePast, 'pkg must be rewritten with the fresh time');
    assert.equal(updateCalls.length, 1, 'the backend must be told about the corrected schedule');
    assert.equal(updateCalls[0][0], 'job-42');
    assert.equal(updateCalls[0][1].listing_schedule_at, pkg.listing_schedule_at);
  }

  console.log('schedule refresh tests passed');
})().catch((error) => { console.error(error); process.exitCode = 1; });
