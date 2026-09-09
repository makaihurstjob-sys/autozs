from pathlib import Path
p=Path('tools/chrome-extension/background.js');s=p.read_text(encoding='utf-8');a=s.index('  const cookies = await chrome.cookies.getAll',s.index('async function clearHomeDepotBatchState'));b=s.index('\n}\n',a);s=s[:a]+'''  // Source refresh shares this profile with checkout and tracking. Removing
  // cookies or site storage here signs the account out between tracking checks.
  if (chrome.browsingData?.remove) {
    await chrome.browsingData.remove(
      { origins: ["https://www.homedepot.com"] },
      { cache: true, cacheStorage: true }
    );
  }
  return { cleared: 0, failed: 0, skipped: false, sessionPreserved: true };'''+s[b:];p.write_text(s,encoding='utf-8')
p=Path('tools/chrome-extension/content.js');s=p.read_text(encoding='utf-8');s=s.replace('Cleared ${Number(cleanup.cleared || 0)} Home Depot cookie(s), cache, and site data; retrying once...', 'Cleared Home Depot cache while preserving sign-in; retrying once...');p.write_text(s,encoding='utf-8')
p=Path('tools/chrome-extension/background.test.js');s=p.read_text(encoding='utf-8');a=s.index('  if (cleanup.cleared !== 5');b=s.index('  const reportFilename',a);s=s[:a]+'''  if (cleanup.cleared !== 0 || removedCookies.length !== 0 || !cleanup.sessionPreserved) {
    throw new Error("Source cleanup must preserve all Home Depot cookies.");
  }
  const assertCacheOnly = () => {
    for (const removal of browsingDataRemovals) {
      const flags = removal.dataToRemove;
      if (!flags.cache || !flags.cacheStorage || Object.keys(flags).some(key => !["cache", "cacheStorage"].includes(key))) {
        throw new Error("Cleanup must preserve cookies, local storage, IndexedDB and service workers.");
      }
    }
    if (removedCookies.length) throw new Error("Batch cleanup removed account cookies.");
  };
  assertCacheOnly();
  const before = browsingDataRemovals.length;
  await context.ensureHomeDepotBatchState("refresh-batch-one");
  await context.ensureHomeDepotBatchState("refresh-batch-one");
  if (browsingDataRemovals.length !== before + 1) throw new Error("Expected one cleanup per batch.");
  await context.ensureHomeDepotBatchState("refresh-batch-two");
  if (browsingDataRemovals.length !== before + 2) throw new Error("Expected cleanup for the next batch.");
  assertCacheOnly();
'''+s[b:];p.write_text(s,encoding='utf-8')
