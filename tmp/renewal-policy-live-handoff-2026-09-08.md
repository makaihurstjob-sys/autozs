# Renewal pruning live verification — 2026-09-08 20:52 UTC

Permanent pruning and allowance guard enabled on live AUTOZS API. No Master Dashboard deployment touched.

Verified eBay End result batches 229 (1), 230 (15), 231 (15), 232 (17), 233 (1): total 49 completed end_zero_view jobs. Batch 230 original eBay CSV re-fetched through Chrome downloads and explicitly contains End,Success for all 15 rows. Other batches reconciled by strict End result importer. 48 of the 49 legacy zero-stock pruning records now ended; remaining item 800363536714 has 1 fresh view, so excluded. Last stale item 800456008929 checked in Seller Hub filtered active list: 0 views, quantity 0. Captured through listing-views API, ended successfully in batch 233. All ended records blocked from automatic relisting.

Fresh allowance 2026-09-08T20:51:46.626Z: total 250, used 148, reserved renewals 81, queued jobs 6, buffer 5, additional capacity 10. Publishing unpaused after verification; worker claimed job 299/product 138, schedule automatically advanced to 2026-09-08 17:36 Eastern. Do not claim completion of remaining publishing retries: job 299 currently running; 303,305,306,311,313 were queued. Job 297 previous Type issue and job 289 placeholder brand remain separate follow-ups; see earlier session evidence.

Verified worker alarms: pruning every 15 minutes, allowance hourly, active sync polling every 2 minutes (server refresh interval applies). Policy requires fresh views and two-hour renewal window; legacy cleanup separate. 7 policy tests and browser allowance, schedule-field, specifics-search tests passed this turn. Prior 84-test policy run retained in tmp/policy-test-results.txt.

Current audit scripts: tmp/pruning-final-audit.py, tmp/policy-current-audit.py. CDP port 9225, extension ainpidpkelkbggebjijlcmmdcdgoggpg, API 127.0.0.1:8000, DB C:/AutoZS/data/autozs.db. Preserve pre-existing dirty changes. Existing seller hub filtered inspection tab may still be open; no worker reload performed.
