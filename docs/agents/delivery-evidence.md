# Delivery page evidence recovery

Base: 4f3eafd. Worktree: C:/AutoZS/worktrees/delivery-evidence-20260912.

Preserved and completed interrupted background changes. Injected page actions now return an explicit success/error envelope, so a page exception retains its actual message rather than disappearing into Missing delivery page evidence. Returned evidence must contain the expected action acknowledgement, or both inspection booleans. Missing/null frames remain hard failures.

The page recognizes exact Log In guest controls alongside Sign In. Product preparation selects a unique exact Delivery control, excluding Delivery Details and Delivery to ZIP controls; duplicate exact matches still fail. Quantity ambiguity is checked before the Delivery click.

Validation: `node --test tools/delivery-check-extension/background.test.js tools/delivery-check-extension/page.test.js` passed 30/30 tests. Both fixtures are in-memory Node VM mocks, with fake Chrome, fetch and DOM; no network, live database, environment credentials, services or browser resources were accessed. `git diff --check` passed.

Coverage includes preservation of page/frame errors, malformed evidence, lost mutation acknowledgements across restart, and transient errors after Add/Remove followed by reconciliation without replay. Existing lease, retry, cart ownership, cleanup and uncertain API completion coverage also passes.

Limitations: mocked controls do not establish compatibility with the current supplier DOM or confirm availability in ZIP 84532. A product whose fulfillment control has additional label text will remain blocked until its DOM can be inspected safely; there is no broad text fallback. The guest-session signal remains the existing visible sign-in-control heuristic, now also accepting Log In. No paused live state was cleared and no extension was activated. Coordinator should integrate, verify the dedicated profile/cart state and perform one scoped live quote cycle before claiming live readiness.
