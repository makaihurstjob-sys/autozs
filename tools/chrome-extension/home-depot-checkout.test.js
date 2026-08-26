const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/home-depot-checkout.js`, "utf8");
const context = {
  console,
  URL,
  URLSearchParams,
  location: { hostname: "example.com", search: "", pathname: "/" },
};
vm.createContext(context);
vm.runInContext(source, context);

const expected = context.autozsExpectedSupplierSubtotal({
  items: [{ unit_price: 12.5, quantity: 2 }, { unit_price: 4.99, quantity: 1 }],
});
if (expected !== 29.99) {
  throw new Error(`Expected supplier subtotal 29.99, got ${expected}`);
}
if (!context.autozsCheckoutPriceMismatch(2.67, 192.24)) {
  throw new Error("Expected square-foot/case price mismatch to block checkout.");
}
if (context.autozsCheckoutPriceMismatch(20, 20.03)) {
  throw new Error("Expected a three-cent rendering difference to stay within checkout tolerance.");
}
if (context.autozsCheckoutMoney("Subtotal $1,234.56") !== 1234.56) {
  throw new Error("Expected checkout money parser to support comma-separated totals.");
}
const confirmation = context.autozsHomeDepotConfirmation(
  "https://www.homedepot.com/order-confirmation/?cartId=HB100305747500&orderId=WK36081870",
  "Thank you. Your Order Total $21.34"
);
if (!confirmation || confirmation.externalOrderId !== "WK36081870") {
  throw new Error("Expected Home Depot's order-confirmation URL to yield its external order ID.");
}
if (context.autozsHomeDepotConfirmation("https://www.homedepot.com/checkout/?orderId=WK36081870", "$21.34")) {
  throw new Error("Expected a non-confirmation Home Depot page not to reconcile an order.");
}
if (context.autozsConfirmationTotal("Thank you. Total $21.34", 21.34) !== 21.34) {
  throw new Error("Expected an exact approved confirmation total to pass.");
}
if (context.autozsConfirmationTotal("Thank you. Total $21.35", 21.34) !== null) {
  throw new Error("Expected a confirmation total above the approved amount to fail closed.");
}
const shippedObservation = context.autozsHomeDepotTrackingObservation(
  "https://www.homedepot.com/order/view/orderdetails?orderId=WK36081870",
  "Order WK36081870 Shipped via UPS Tracking Number: 1Z 999 AA1 01 2345 6784"
);
if (!shippedObservation || shippedObservation.status !== "shipped" || shippedObservation.carrier !== "UPS"
  || shippedObservation.trackingNumber !== "1Z999AA10123456784") {
  throw new Error(`Expected an exact Home Depot shipment observation, got ${JSON.stringify(shippedObservation)}`);
}
if (context.autozsHomeDepotTrackingObservation(
  "https://www.homedepot.com/order/view/orderdetails?orderId=WK36081870",
  "Pardon Our Dust Order WK36081870 Shipped via UPS Tracking Number: 1Z999AA10123456784"
)) {
  throw new Error("Expected Home Depot's anti-automation page never to report tracking.");
}
if (!context.autozsHomeDepotTrackingBlocked(
  "https://www.homedepot.com/order/view/orderdetails?orderId=WK36081870&autozs_tracking_poll=1",
  "Pardon Our Dust"
)) {
  throw new Error("Expected a marked Home Depot anti-automation page to trigger tracking cooldown.");
}
if (context.autozsHomeDepotTrackingObservation(
  "https://www.homedepot.com/order/view/orderdetails?orderId=OTHER123",
  "Order WK36081870 Shipped via UPS Tracking Number: 1Z999AA10123456784"
)) {
  throw new Error("Expected a mismatched Home Depot order identity never to report tracking.");
}
const city = context.autozsChooseCheckoutCity(
  [
    { city: "Denver", state: "CO", value: "Denver" },
    { city: "Lakewood", state: "CO", value: "Lakewood" },
  ],
  "Lakewood",
  "CO"
);
if (!city || city.value !== "Lakewood") {
  throw new Error("Expected ZIP-driven city selection to require the exact eBay city/state.");
}
if (context.autozsChooseCheckoutCity([{ city: "Lakewood", state: "CO" }, { city: "Lakewood", state: "CO" }], "Lakewood", "CO")) {
  throw new Error("Expected ambiguous Home Depot city choices to pause checkout.");
}
if (!context.autozsCheckoutAddressMatches(
  { recipient_name: "Jamie Rivera", address_line1: "123 Example Ave.", address_line2: "Apt 4", city: "Lakewood", state: "CO", postal_code: "80226-1234" },
  { recipient_name: "Jamie Rivera", address_line1: "123 Example Ave", address_line2: "Apt 4", city: "Lakewood", state: "CO", postal_code: "80226" }
)) {
  throw new Error("Expected normalized Home Depot read-back to match the eBay shipping address.");
}
if (context.autozsCheckoutAddressMatches(
  { recipient_name: "Jamie Rivera", address_line1: "123 Example Ave", address_line2: "", city: "Lakewood", state: "CO", postal_code: "80226" },
  { recipient_name: "Jamie Rivera", address_line1: "123 Example Ave", address_line2: "", city: "Denver", state: "CO", postal_code: "80226" }
)) {
  throw new Error("Expected a wrong city within the same ZIP to block checkout.");
}
const staticCityState = context.autozsCheckoutStaticCityState("ZIP Code\n87508\nCity, State\nSanta Fe, NM\nContinue");
if (!staticCityState || staticCityState.city !== "Santa Fe" || staticCityState.state !== "NM") {
  throw new Error("Expected signed-in Home Depot checkout to verify its static ZIP-driven city/state result.");
}
for (let pass = 1; pass <= 3; pass += 1) {
  const delivery = context.autozsCheckoutDeliveryState(
    "Delivery Options\nYour Delivery Cost: FREE\nWednesday, Aug 26\nFREE\nContinue",
    true,
    false
  );
  if (!delivery.visible || !delivery.enabled || !delivery.free || delivery.unavailable) {
    throw new Error(`Expected guarded free-delivery regression pass ${pass} to succeed.`);
  }
}
const hiddenDelivery = context.autozsCheckoutDeliveryState("Delivery Options\nPayment Method", false, false);
if (hiddenDelivery.enabled) throw new Error("Expected a hidden delivery button to remain unusable.");
const unavailableDelivery = context.autozsCheckoutDeliveryState(
  "Delivery Options\nYour Delivery Cost can't be calculated at this time. Scheduled Delivery is no longer available.",
  true,
  true
);
if (!unavailableDelivery.unavailable || unavailableDelivery.enabled) {
  throw new Error("Expected unavailable delivery to block checkout.");
}
const totals = context.autozsCheckoutTotals("Subtotal $19.97 Shipping $0.00 Estimated Tax $1.60 Order Total $21.57");
if (totals.subtotal !== 19.97 || totals.shipping !== 0 || totals.tax !== 1.6 || totals.total !== 21.57) {
  throw new Error(`Expected checkout totals to parse, got ${JSON.stringify(totals)}`);
}
if (!context.autozsCheckoutTotalsAreSafe(totals, 19.97, 21.57)) {
  throw new Error("Expected a recomposed final total at the approved ceiling to be safe.");
}
const liveTotals = context.autozsCheckoutTotals("Your Order\nSubtotal\n$19.97\nDelivery\nFREE\nEstimated Sales Tax*\n$1.37\nTotal\n$21.34");
if (liveTotals.subtotal !== 19.97 || liveTotals.shipping !== 0 || liveTotals.tax !== 1.37 || liveTotals.total !== 21.34) {
  throw new Error(`Expected the live Home Depot order-summary labels to parse, got ${JSON.stringify(liveTotals)}`);
}
if (!context.autozsCheckoutTotalsAreSafe(liveTotals, 19.97, 21.57)) {
  throw new Error("Expected the live Home Depot total below the approved ceiling to be safe.");
}
if (!context.autozsHomeDepotCheckoutErrorPage("Error Page", "")) {
  throw new Error("Expected Home Depot's explicit Error Page to trigger checkout cooldown.");
}
if (context.autozsHomeDepotCheckoutErrorPage("Checkout", "Delivery Options Payment Method")) {
  throw new Error("Expected an ordinary checkout stage to remain eligible for guarded automation.");
}
const discountedCart = "CART (1) Total: $19.97 Your Order Subtotal $22.97 Savings -$3.00 Delivery FREE Total $19.97";
if (context.autozsCartPayableSubtotal(discountedCart) !== 19.97) {
  throw new Error("Expected cart validation to use the payable merchandise total after Home Depot savings.");
}
if (context.autozsCheckoutTotalsAreSafe({ ...totals, total: 21.58 }, 19.97, 21.57)) {
  throw new Error("Expected a final total above the approved ceiling to block checkout.");
}
if (!source.includes('AUTOZS_CHECKOUT_CART_REBUILD_KEY')) {
  throw new Error("Expected guarded checkout to track its one permitted cart rebuild.");
}
if (!source.includes('attempt < 12') || !source.includes('remove_from_cart')) {
  throw new Error("Expected stale-cart cleanup to be bounded and use the native Remove allow-list action.");
}
if (!source.includes('if (/there[\'â€™]s nothing in here yet/i.test')) {
  if (!source.includes('if (visiblyEmpty) break')) {
    throw new Error("Expected a disappearing Remove control to count as success only after the cart is visibly empty.");
  }
}
if (!source.includes('autozsWaitForCheckoutButton(/^add to cart$/i, 20, 500)')) {
  throw new Error("Expected checkout to wait for Home Depot's asynchronously rendered Add to Cart control.");
}
if (!source.includes('const attempts = markedPoll ? 20 : 1')) {
  throw new Error("Expected Home Depot tracking pages to use a bounded 20-second render observation window.");
}
if (!source.includes('history.replaceState(history.state, "", guardedUrl.href)')) {
  throw new Error("Expected secure checkout navigation to retain its session-bound guarded order identity.");
}
if (!source.includes('autozsNativeCheckoutClick(supplierOrderId, "use_new_card")') || !source.includes('includes(`****${lastFour}`)')) {
  throw new Error("Expected secured card entry to apply and verify the approved card before owner review.");
}
if (!source.includes('autozsNativeCheckoutClick(supplierOrderId, "delivery_continue")')) {
  throw new Error("Expected delivery to use its exact Continue control instead of the stale address Continue.");
}
if (!source.includes("selected saved card does not match the approved checkout card")) {
  throw new Error("Expected a selected saved card to be verified against the approved checkout credential.");
}
if (!source.includes('autozsNativeCheckoutClick(supplierOrderId, "add_new_card")')) {
  throw new Error("Expected a mismatched saved card to open the approved new-card form without touching Place Order.");
}
if (!source.includes('iframe#iframe-credit-card-payment-field')) {
  throw new Error("Expected Home Depot's outer secured-card frame to signal that nested Fiserv fields are ready.");
}
if (!source.includes('autozsNativeCheckoutClick(supplierOrderId, "edit_address")')) {
  throw new Error("Expected a matching saved delivery address to be reopened for exact field verification.");
}
if (!source.includes("pickup checkout was not allowed")) {
  throw new Error("Expected cart checkout to require visibly confirmed free delivery instead of supplier pickup.");
}
if (!source.includes("if (!cartDeliveryConfirmed) await autozsNativeCheckoutClick")) {
  throw new Error("Expected an already-confirmed free-delivery cart to avoid a redundant fulfillment click.");
}
if (/\.click\(\)[\s\S]{0,80}place order/i.test(source)) {
  throw new Error("The guarded checkout script must never click Place order.");
}
if (!source.includes('"pointer-events:none"')) {
  throw new Error("The checkout status overlay must not intercept trusted Home Depot clicks.");
}

console.log("guarded Home Depot checkout tests ok");
