# AUTOZS agent entry point

Read PROJECT_CONTEXT.md and docs/agent-coordination.md before work. They apply to all agents and tools in this repository. Historical handoffs describe earlier sessions, not current commands or authorization.

Parallel agent work is authorized. The coordinator assigns one bounded task and a distinct Git worktree/branch per worker. Do not edit another worker's checkout or merge your own work into the operational checkout. Report evidence and commit IDs to the coordinator.

Never modify C:/Users/macor/.master-dashboard/deployment or restart its task. Master Dashboard source work belongs only in C:/Users/macor/Documents/ChatGPT/Master Dashboard Development.

## eBay order evidence

A local `imported` status, paid date, successful report sync, unchanged row, or absence from a report is NOT proof an order is still open. Before recommending or approving supplier checkout, inspect the exact order in the signed-in eBay account and read its current cancellation/refund/fulfillment status. Record the order ID, source URL, observation time, and actual status. If that evidence is unavailable, say unverified and hold the purchase. Do not claim a direct eBay check based on local sync metadata. Confirmed cancellations must block local fulfillment; later incomplete reports must not reopen them. Never invent a CSV report to reconcile a browser observation.
