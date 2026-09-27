# Place Order button

Development checkout: C:/AutoZS/worktrees/place-order-button-20260926; base ade93a4.

Replaces Approve checkout with one Place Order click for draft supplier orders. The API records permission bound to the exact approval timestamp in the same transaction as queuing. Legacy approval cannot create this permission. Claim and final submission both require it; legacy queued orders return to draft for an explicit click. Existing final financial, cancellation, freshness, lease, duplicate and durable budget checks remain in force.

The endpoint requires a loopback caller, local HTTP(S) browser origin and explicit action header. This is local-dashboard access restriction, not authenticated owner identity: AUTOZS has no owner login. Other programs or people with access to the local Windows session remain inside that trust boundary.

The button queues execution by the existing browser worker; it does not bypass the automation-enabled setting or prove live checkout completion. No policy enabled, no API restart, no extension reload, and no real purchase performed. Source remains in the development worktree pending integration. Downloads launcher remains a separate follow-up.

Validation: 14 purchase-submission tests and 33 budget/policy tests passed (47 total). Dashboard inline JavaScript parsed with Node vm.Script; git diff --check passed. Initial combined run exposed a minimal-fixture dependency when the permission check preceded the reserved-order guard; restored reserved-order-first ordering and reran budget/policy successfully. No live browser test performed.


Launcher continuation: added tools/Start-AUTOZS-Orders.ps1 and Open AUTOZS Orders.cmd, installed under C:/Users/macor/Downloads/dashboard, and packaged in conversation dropoff. Added tab=orders and order query handling to dashboard. Launcher uses GET only, excludes locally closed/purchased/in-flight orders, labels eligibility unverified, and refuses the legacy live flow. Live CheckOnly confirmed refusal because deployment lacks the new flow. Mock selection chose open order 10 over cancelled 11 and purchased 12; no browser opened. Dashboard JavaScript parse and diff check passed. No live services changed.

