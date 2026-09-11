# Cart delivery quote tracking

The browser extension observes Home Depot `/mycart/home` without changing the cart or destination. It records only a single identifiable product, explicit quantity, one consistent `Delivering to` ZIP, and one delivery charge in `Your Order`. Two observations three seconds apart must match. Ambiguous, loading, unavailable and mixed-cart pages are skipped. Only product URL, ZIP, quantity and charge leave the page; buyer names, full addresses and payment details are not collected.

`POST /delivery-quotes/cart` stores the latest quote per supplier product, ZIP and quantity. `GET /delivery-quotes/products/{product_id}` exposes quotes, 24-hour freshness and the blocking reason. Startup creates the new table using the application's existing metadata initialization.

Any paid quote blocks new listing jobs and is checked again when an existing job starts. The reason also appears in listing readiness. A free observation at another ZIP or quantity cannot clear it. Old paid quotes stay blocking until the same ZIP and quantity are observed free. Free samples never certify nationwide delivery. Existing live listings are not automatically removed by this change.

Activation requires loading the updated API and reloading the extension and cart page. Tests use isolated databases and simulated page evidence; live capture has not yet been validated.

Remaining: a dedicated browser worker that visits carts before listing across configured representative ZIPs, protects any fulfillment cart, recovers interrupted checks and holds unsampled products pending verification. The current observer learns from carts that are visited; it does not perform those visits itself. Buyer-specific checkout verification remains required.
