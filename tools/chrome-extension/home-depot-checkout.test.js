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

console.log("guarded Home Depot checkout tests ok");
