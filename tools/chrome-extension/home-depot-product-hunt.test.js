const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/home-depot-product-hunt.js`, "utf8");
const context = {
  URL,
  URLSearchParams,
  console,
  globalThis: null,
  location: {
    hostname: "example.com",
    href: "https://example.com/",
    pathname: "/",
    search: "",
  },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);

const helpers = context.__autozsHomeDepotProductHunt;
if (!helpers) throw new Error("Expected product-hunt helpers to be exported.");

const canonical = helpers.canonicalHomeDepotProductUrl(
  "https://www.homedepot.com/p/Husky-Industrial-Pistol-Nozzle-10502HD/100000123?MERCH=REC-_-foo"
);
if (canonical !== "https://www.homedepot.com/p/Husky-Industrial-Pistol-Nozzle-10502HD/100000123") {
  throw new Error(`Expected canonical Home Depot URL, got ${canonical}`);
}
if (helpers.canonicalHomeDepotProductUrl("https://example.com/p/Test/100000123")) {
  throw new Error("Expected non-Home-Depot URL to be rejected.");
}

const combined = helpers.detectProductBadges("Top Rated Exclusive product");
if (!combined.topRated || !combined.exclusive || combined.bestSeller) {
  throw new Error(`Expected combined badges, got ${JSON.stringify(combined)}`);
}
const bestSeller = helpers.detectProductBadges("Best Seller");
if (!bestSeller.bestSeller) throw new Error("Expected Best Seller badge.");

const product = { badges: { topRated: true, exclusive: true, bestSeller: false } };
if (!helpers.matchesFilter(product, "top-rated-exclusive")) {
  throw new Error("Expected combined product to match Top Rated + Exclusive.");
}
if (helpers.matchesFilter(product, "top-rated")) {
  throw new Error("Expected combined product to stay out of the Top Rated-only bucket.");
}

console.log("home-depot product hunt tests passed");
