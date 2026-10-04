# Depop default boosting, October 3, 2026

Owner requested future listings boosted at12%, and reports existing listings already boosted. Replaced forced opt-out with verified opt-in. Exact boost section must show one percentage equal to12; missing, ambiguous or changed rates block form readiness and both Post checks. No pricing, existing listing or scheduler changes.

Isolated commit49229ef integrated as1f4d0d1. Eight Depop tests plus background test passed in both checkouts, including12 boost scenarios and6 submission scenarios. Diff check passed. Extension reloaded; loaded depop-fill.js SHA256 ab856a1e3e2d3067d574b86b56a196bf470b4dfc82ed8075c8b9b6454e02ce25 matches operational file. Completed Browser Bridge inspection showed Pay an extra12% fee, only if you sell. Live exact helper on blank form returned before=false, after=true, verified=true. No Post performed. Scheduler and pending storage absent; jobs5-8 queued attempts0. Actual new boosted publication remains untested.

Depop fee reference: https://depophelp.zendesk.com/hc/en-gb/articles/10110299060753-Boosted-Listings
