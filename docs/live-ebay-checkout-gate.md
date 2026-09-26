# Live eBay checkout verification

The checkout worker opens the exact Seller Hub order detail page and checks the signed-in seller account, explicit paid date, ship-by status, and empty tracking. Cancellation, refund, existing shipment, unknown page state, missing identity, and failed evidence persistence stop the handoff.

Evidence is stored in ebay_checkout_verifications. The API rejects mismatched identities/URLs, observations older than 60 seconds at receipt, and evidence older than 120 seconds at use. Both supplier claim and payment credential release require fresh eligible evidence. Terminal observations cannot be overwritten by a later eligible observation. Unknown observations require review and reapproval.

The browser rechecks before claiming, before credentials, and before marking checkout ready for owner review. The Home Depot flow still does not click Place order. This change does not enable automatic approvals or automatic purchases.

Implementation trusts the localhost browser worker observation; it is not cryptographic proof from an eBay API. English Seller Hub layout changes fail closed. A missing browser/session requires intervention. Real cancelled order 04-15204-72108 and already-shipped order 02-15229-83590 were read directly and correctly rejected by the classifier. No eligible live purchase was exercised.
