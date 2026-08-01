const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/capture.js`, "utf8");

function runCapture(visibleText, {
  offerPrice = "17.97",
  productName = "HDX 13 Gallon Reinforced Top Drawstring Fresh Scented Tall Kitchen Trash Bags 200 Count",
  standardPrice = null,
  href = "https://www.homedepot.com/p/HDX-13-Gallon-Reinforced-Top-Drawstring-Fresh-Scented-Tall-Kitchen-Trash-Bags-with-20-PCR-200-Count-HDR13XHFN200W-F/331012931?ea_auto_import=1&auto_download_test=1&MERCH=REC",
  hostname = "www.homedepot.com",
  pathname = "/p/HDX-13-Gallon-Reinforced-Top-Drawstring-Fresh-Scented-Tall-Kitchen-Trash-Bags-with-20-PCR-200-Count-HDR13XHFN200W-F/331012931",
} = {}) {
  const context = {
    console,
    URL,
    window: {
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href,
      hostname,
      pathname,
    },
    document: {
      body: { innerText: visibleText },
      documentElement: { innerHTML: "" },
      images: [],
      querySelector: (selector) => selector === "#standard-price" && standardPrice !== null
        ? { innerText: standardPrice }
        : null,
      querySelectorAll: (selector) => {
        if (selector === 'script[type="application/ld+json"]') {
          return [
            {
              textContent: JSON.stringify({
                "@type": "Product",
                name: productName,
                offers: offerPrice === null ? undefined : { price: offerPrice },
                image: ["https://images.thdstatic.com/productImages/hdx-trash-bags-front.jpg"],
              }),
            },
          ];
        }
        return [];
      },
    },
  };
  vm.createContext(context);
  vm.runInContext(`${source}; result = captureSourceProductFromPage();`, context);
  return context.result;
}

const freeShippingWithSubscription = runCapture(`
HDX 13 Gallon Reinforced Top Drawstring Fresh Scented Tall Kitchen Trash Bags
$17.97
Free Delivery
Get it by tomorrow
Subscribe and Get 5% off
Subscription price
$17.07
`);

if (freeShippingWithSubscription.source_price !== 17.97) {
  throw new Error(`Expected source price 17.97, got ${freeShippingWithSubscription.source_price}`);
}
if (freeShippingWithSubscription.detected_shipping !== 0) {
  throw new Error(`Expected free shipping, got ${freeShippingWithSubscription.detected_shipping}`);
}
if (freeShippingWithSubscription.subscription_discount_percent !== 5) {
  throw new Error(`Expected 5% subscription discount, got ${freeShippingWithSubscription.subscription_discount_percent}`);
}
if (freeShippingWithSubscription.source_url.includes("ea_auto_import") || freeShippingWithSubscription.source_url.includes("auto_download_test")) {
  throw new Error(`Expected internal params stripped from source URL, got ${freeShippingWithSubscription.source_url}`);
}
if (freeShippingWithSubscription.source_url.includes("?") || freeShippingWithSubscription.source_url.includes("#")) {
  throw new Error(`Expected Home Depot product tracking parameters to be stripped, got ${freeShippingWithSubscription.source_url}`);
}

const recommendationOnlyPrice = runCapture(
  `
Milwaukee M18 PACKOUT Wet/Dry Vacuum
This product is currently unavailable.
Customers also viewed
Milwaukee M18 replacement kit
$249.00
`,
  { offerPrice: null, productName: "Milwaukee M18 PACKOUT Wet/Dry Vacuum" }
);
if (recommendationOnlyPrice.source_price !== null) {
  throw new Error(`Expected recommendation-only price to be rejected, got ${recommendationOnlyPrice.source_price}`);
}

let rejectedLowesScaffold = false;
try {
  runCapture("Lowe's sample product\n$19.98", {
    hostname: "www.lowes.com",
    pathname: "/pd/Project-Source-Sample/5012345678",
    href: "https://www.lowes.com/pd/Project-Source-Sample/5012345678?cm_mmc=tracking",
  });
} catch (error) {
  rejectedLowesScaffold = /not enabled yet/i.test(error.message);
}
if (!rejectedLowesScaffold) {
  throw new Error("Expected Lowe's browser capture to remain disabled while scaffolded.");
}

let rejectedHomeDepotErrorPage = false;
try {
  runCapture(`
#1 Home Improvement Retailer
Oops!! Something went wrong. Please refresh page
Refresh
How doers get more done
Need Help? Visit our Customer Service Center
`);
} catch (error) {
  rejectedHomeDepotErrorPage = /Home Depot showed an error page/i.test(error.message);
}
if (!rejectedHomeDepotErrorPage) {
  throw new Error("Expected Home Depot error pages to be rejected before import.");
}
if (freeShippingWithSubscription.minimum_order_quantity !== 1) {
  throw new Error(`Expected ordinary products to default to minimum quantity 1, got ${freeShippingWithSubscription.minimum_order_quantity}`);
}

const minimumOrderTwo = runCapture(
  `
Ornamental Mouldings Unfinished Natural Ash Wood Board
$14.19
Minimum Order Quantity: 2
Free Delivery
`,
  { offerPrice: "14.19", productName: "Ornamental Mouldings Unfinished Natural Ash Wood Board" }
);
if (minimumOrderTwo.source_price !== 14.19) {
  throw new Error(`Expected per-unit source price 14.19, got ${minimumOrderTwo.source_price}`);
}
if (minimumOrderTwo.minimum_order_quantity !== 2) {
  throw new Error(`Expected minimum order quantity 2, got ${minimumOrderTwo.minimum_order_quantity}`);
}

const flooringCasePrice = runCapture(
  `
Mohawk Elite - Azure Edge - Blue Commercial 24 x 24 in. Glue-Down Carpet Tile Square (72 sq. ft.)
Covers 72 sq. ft.
$2.67
/sq. ft.
($192.24 /case)
Free Delivery
`,
  {
    offerPrice: "2.67",
    productName: "Mohawk Elite - Azure Edge - Blue Commercial 24 x 24 in. Glue-Down Carpet Tile Square (72 sq. ft.)",
  }
);
if (flooringCasePrice.source_price !== 192.24) {
  throw new Error(`Expected purchasable case price 192.24 instead of square-foot rate, got ${flooringCasePrice.source_price}`);
}
if (flooringCasePrice.capture_debug.purchase_price_basis !== "explicit-package-total") {
  throw new Error(`Expected explicit package-price basis, got ${JSON.stringify(flooringCasePrice.capture_debug)}`);
}
if (flooringCasePrice.source_purchase_unit !== "case" || flooringCasePrice.source_bulk_package !== true) {
  throw new Error(`Expected case products to be blocked, got ${JSON.stringify(flooringCasePrice.capture_debug)}`);
}

const computedFlooringCasePrice = runCapture(
  `
Mohawk Commercial Carpet Tile Square
Covers 72 sq. ft.
$2.67 /sq. ft.
Free Delivery
`,
  { offerPrice: "2.67", productName: "Mohawk Commercial Carpet Tile Square" }
);
if (computedFlooringCasePrice.source_price !== 192.24) {
  throw new Error(`Expected computed 72 sq. ft. case price 192.24, got ${computedFlooringCasePrice.source_price}`);
}
if (computedFlooringCasePrice.source_purchase_unit !== "coverage" || computedFlooringCasePrice.source_bulk_package !== true) {
  throw new Error(`Expected coverage-priced products to be blocked, got ${JSON.stringify(computedFlooringCasePrice.capture_debug)}`);
}

const normalPageWithRefreshCopy = runCapture(`
HDX replacement hardware
$17.97
Please refresh page details after choosing a delivery location.
Free Delivery
`);
if (normalPageWithRefreshCopy.source_price !== 17.97) {
  throw new Error("Expected refresh wording without the Home Depot Oops screen to remain importable.");
}

const paidShipping = runCapture(`
Project panel
$49.33
Delivery
$55.00
`);

if (paidShipping.detected_shipping !== 55) {
  throw new Error(`Expected paid shipping 55, got ${paidShipping.detected_shipping}`);
}

const paidDeliveryBeatsGenericFreeShipping = runCapture(`
Everbilt replacement hardware
$10.96
Free shipping available on qualifying items
Delivery
$2.99
Get it by Tuesday
`);

if (paidDeliveryBeatsGenericFreeShipping.detected_shipping !== 2.99) {
  throw new Error(`Expected paid delivery 2.99 to beat generic free shipping, got ${paidDeliveryBeatsGenericFreeShipping.detected_shipping}`);
}

const freeStandardDeliveryBeatsOrderThreshold = runCapture(`
Everbilt 1 in. MPT x 1 in. Barb Brass Adapter Fitting
$22.98
Delivery
Tomorrow
16 available
FREE
Get It Faster
FREE Delivery Today with $25+ of eligible items
Today by 8pm
$2.99
`);

if (freeStandardDeliveryBeatsOrderThreshold.detected_shipping !== 0) {
  throw new Error(`Expected normal free delivery instead of the $25 order threshold, got ${freeStandardDeliveryBeatsOrderThreshold.detected_shipping}`);
}

const freeStandardDeliveryBeatsThreeHourFee = runCapture(`
RIDGID 9-Amp 7 in. Blade Corded Wet Tile Saw with Stand R4031S
$369.00
Delivery
Tomorrow
FREE
Get It Faster
Get it within 3 hours
$7.00
`);

if (freeStandardDeliveryBeatsThreeHourFee.detected_shipping !== 0) {
  throw new Error(`Expected normal free delivery instead of the three-hour $7 fee, got ${freeStandardDeliveryBeatsThreeHourFee.detected_shipping}`);
}

const threeHourFeeIsNotStandardShipping = runCapture(`
ROBERTS 630 sq. ft. Underlayment
$165.41
Get It Faster
Delivery within 3 hours
$7.00
`);

if (threeHourFeeIsNotStandardShipping.detected_shipping !== null) {
  throw new Error(`Expected an isolated accelerated-delivery fee to be ignored, got ${threeHourFeeIsNotStandardShipping.detected_shipping}`);
}

const unavailableDeliveryDoesNotBorrowLaterPrice = runCapture(`
Vigoro 6 lb. Organic Rose and Flower Plant Food 4-7-3
$10.97
Pickup at Coral Springs
Limited Stock
Delivery
Unavailable
Check Nearby Stores
Frequently Bought Together
$15.65
`);

const plainOutOfStockIsUnavailable = runCapture(`
Back to the Roots Organic Bulk Potting Mix Soil 4-Pack
$29.08
Bag Capacity/Dry Volume (qt): 120 qt
Out of Stock
Receive an email when this item is back in stock.
Notify Me
`);
if (plainOutOfStockIsUnavailable.source_in_stock !== false) {
  throw new Error(
    `Expected a plain Out of Stock heading to mark the source unavailable, got ${plainOutOfStockIsUnavailable.source_in_stock}`
  );
}
if (plainOutOfStockIsUnavailable.detected_shipping !== null) {
  throw new Error(
    `Expected an out-of-stock item to have no shipping quote, got ${plainOutOfStockIsUnavailable.detected_shipping}`
  );
}

const regionRestrictedItemIsUnavailable = runCapture(`
FOXFARM Ocean Forest 40 lbs. 6.3-6.8 pH Plant Garden Potting Soil Mix
$38.35
Not Available in Florida
Please change your store or ZIP Code to purchase
Free & Easy Returns In Store or Online
`);
if (regionRestrictedItemIsUnavailable.source_in_stock !== false) {
  throw new Error(
    `Expected a region-restricted item to be unavailable, got ${regionRestrictedItemIsUnavailable.source_in_stock}`
  );
}
if (regionRestrictedItemIsUnavailable.detected_shipping !== null) {
  throw new Error(
    `Expected a region-restricted item to have no shipping quote, got ${regionRestrictedItemIsUnavailable.detected_shipping}`
  );
}

if (unavailableDeliveryDoesNotBorrowLaterPrice.detected_shipping !== null) {
  throw new Error(
    `Expected unavailable delivery to have no shipping price, got ${unavailableDeliveryDoesNotBorrowLaterPrice.detected_shipping}`
  );
}
if (unavailableDeliveryDoesNotBorrowLaterPrice.source_in_stock !== false) {
  throw new Error(
    `Expected unavailable delivery to mark the source unavailable, got ${unavailableDeliveryDoesNotBorrowLaterPrice.source_in_stock}`
  );
}

const specialBuy = runCapture(`
DEWALT Atomic 20V Max Lithium-Ion Brushless Cordless Compact 1/4 in. Impact Driver Kit
4th of July Sale
SPECIAL BUY
$99 00
Was $179.00
Save $80.00 (45%)
Pay $74 after $25 OFF your total qualifying purchase upon opening a new card.
Free Delivery
`);

if (specialBuy.source_price !== 99) {
  throw new Error(`Expected Home Depot Special Buy price 99, got ${specialBuy.source_price}`);
}

const splitSpecialBuy = runCapture(`
DEWALT Atomic 20V Max Lithium-Ion Brushless Cordless Compact 1/4 in. Impact Driver Kit
4th of July Sale
SPECIAL
BUY
$99
00
Was $179.00
Save $80.00 (45%)
Pay $74 after $25 OFF your total qualifying purchase upon opening a new card.
Free Delivery
`);

if (splitSpecialBuy.source_price !== 99) {
  throw new Error(`Expected split Home Depot Special Buy price 99, got ${splitSpecialBuy.source_price}`);
}

const saleBannerWithoutSpecialBuyText = runCapture(`
DEWALT Atomic 20V Max Lithium-Ion Brushless Cordless Compact 1/4 in. Impact Driver Kit
4th of July Sale
Shop DEWALT
$99 00 Was $179.00
Save $80.00 (45%)
Pay $74 after $25 OFF your total qualifying purchase upon opening a new card.
Free Delivery
`);

if (saleBannerWithoutSpecialBuyText.source_price !== 99) {
  throw new Error(`Expected Home Depot sale banner price 99, got ${saleBannerWithoutSpecialBuyText.source_price}`);
}

const splitNormalPriceBeatsRoundedStructuredOffer = runCapture(
  `
ROBERTS Laminate and Wood Flooring Installation Kit 10-28
Shop ROBERTS
$
22
97
Free Delivery
`,
  { offerPrice: "22.00", productName: "ROBERTS Laminate and Wood Flooring Installation Kit 10-28" }
);

if (splitNormalPriceBeatsRoundedStructuredOffer.source_price !== 22.97) {
  throw new Error(`Expected split Home Depot visible price 22.97, got ${splitNormalPriceBeatsRoundedStructuredOffer.source_price}`);
}

const splitNormalPriceWithUnitCents = runCapture(
  `
Henry 555 Level Pro 40 lb. Self-Leveling Underlayment 12165
Shop Henry
$39
97 /case
Free Delivery
`,
  { offerPrice: "39.00", productName: "Henry 555 Level Pro 40 lb. Self-Leveling Underlayment 12165" }
);

if (splitNormalPriceWithUnitCents.source_price !== 39.97) {
  throw new Error(`Expected split Home Depot cents with unit price 39.97, got ${splitNormalPriceWithUnitCents.source_price}`);
}

const splitNormalPriceWithSeparateDecimal = runCapture(
  `
ROBERTS Laminate and Wood Flooring Installation Kit
Shop ROBERTS
$
22
.
97
Flooring installation kit for laminate and floating wood floors
`,
  { offerPrice: "22.00", productName: "ROBERTS Laminate and Wood Flooring Installation Kit" }
);

if (splitNormalPriceWithSeparateDecimal.source_price !== 22.97) {
  throw new Error(`Expected split Home Depot decimal-node price 22.97, got ${splitNormalPriceWithSeparateDecimal.source_price}`);
}

const savingsBannerWithSeparateDecimal = runCapture(
  `
SHOP 4TH OF JULY SAVINGS
ROBERTS Laminate and Wood Flooring Installation Kit
Shop ROBERTS
$
22
.
97
Flooring installation kit for laminate and floating wood floors
`,
  { offerPrice: "22.97", productName: "ROBERTS Laminate and Wood Flooring Installation Kit" }
);

if (savingsBannerWithSeparateDecimal.source_price !== 22.97) {
  throw new Error(`Expected Home Depot savings banner split price 22.97, got ${savingsBannerWithSeparateDecimal.source_price}`);
}

const emailSignupDiscount = runCapture(
  `
Prime-Line 30 in. Window Block and Tackle Sash Balance FA 2940
$15.29
Free Delivery
Get $5 off when you sign up for emails.
`,
  { offerPrice: null, productName: "Prime-Line 30 in. Window Block and Tackle Sash Balance FA 2940" }
);

if (emailSignupDiscount.source_price !== 15.29) {
  throw new Error(`Expected product price 15.29 instead of email discount, got ${emailSignupDiscount.source_price}`);
}

const structuredPriceWithoutDollar = runCapture(
  `
Prime-Line 30 in. Window Block and Tackle Sash Balance FA 2940
Get $5 off when you sign up for emails.
`,
  { offerPrice: "15.29", productName: "Prime-Line 30 in. Window Block and Tackle Sash Balance FA 2940" }
);

if (structuredPriceWithoutDollar.source_price !== 15.29) {
  throw new Error(`Expected structured offer price 15.29, got ${structuredPriceWithoutDollar.source_price}`);
}

const globalSavingsFiveDollarOffer = runCapture(
  `
Summer Savings
ROBERTS 7350 Flooring Adhesive
Get $5 off when you sign up for emails
$169.00
Free Delivery
`,
  { offerPrice: "169.00", productName: "ROBERTS 7350 Flooring Adhesive", standardPrice: "$169.00" }
);
if (globalSavingsFiveDollarOffer.source_price !== 169) {
  throw new Error(`Expected the corroborated product price 169 instead of the global $5 offer, got ${globalSavingsFiveDollarOffer.source_price}`);
}
if (globalSavingsFiveDollarOffer.capture_debug.detected_sale_price !== 5 || globalSavingsFiveDollarOffer.capture_debug.sale_price_corroborated) {
  throw new Error(`Expected the uncorroborated $5 sale candidate to be rejected, got ${JSON.stringify(globalSavingsFiveDollarOffer.capture_debug)}`);
}

function runHomeDepotModelImageFilterTest() {
  const actual100 = "https://images.thdstatic.com/productImages/a/svn/milwaukee-power-tool-batteries-48-11-1850-64_100.jpg";
  const actual1000 = "https://images.thdstatic.com/productImages/a/svn/milwaukee-power-tool-batteries-48-11-1850-64_1000.jpg";
  const secondActual = "https://images.thdstatic.com/productImages/b/svn/milwaukee-power-tool-batteries-48-11-1850-e1_600.jpg";
  const unrelated = "https://images.thdstatic.com/productImages/c/svn/milwaukee-wet-dry-vacuums-0970-20-64_600.jpg";
  const context = {
    console,
    URL,
    window: { matchMedia: () => ({ matches: false }) },
    location: {
      href: "https://www.homedepot.com/p/Milwaukee-M18-18-Volt-5-0-Ah-Lithium-Ion-XC-Extended-Capacity-Battery-Pack-48-11-1850/205620421",
      hostname: "www.homedepot.com",
      pathname: "/p/Milwaukee-M18-18-Volt-5-0-Ah-Lithium-Ion-XC-Extended-Capacity-Battery-Pack-48-11-1850/205620421",
    },
    document: {
      body: { innerText: "Milwaukee M18 battery\n$99.00\nFree delivery" },
      documentElement: { innerHTML: [actual1000, unrelated].join(" ") },
      images: [],
      querySelector: () => null,
      querySelectorAll: (selector) => {
        if (selector === 'script[type="application/ld+json"]') {
          return [{
            textContent: JSON.stringify({
              "@type": "Product",
              name: "Milwaukee M18 Battery 48-11-1850",
              model: "48-11-1850",
              offers: { price: "99.00" },
              image: [actual100, secondActual],
            }),
          }];
        }
        return [];
      },
    },
  };
  vm.createContext(context);
  vm.runInContext(`${source}; result = captureSourceProductFromPage();`, context);
  const images = context.result.image_urls.split("\n").filter(Boolean);
  if (images.length !== 2 || images.some((url) => !url.includes("48-11-1850"))) {
    throw new Error(`Expected only two matching Milwaukee model images, got ${JSON.stringify(images)}`);
  }
  if (!images.includes(actual1000) || images.includes(actual100)) {
    throw new Error(`Expected the largest resolution variant, got ${JSON.stringify(images)}`);
  }
}

runHomeDepotModelImageFilterTest();

function runEbayUsernameDetectionTest() {
  const accountElements = [
    {
      textContent: "Hi Makai!",
      getAttribute: () => "",
    },
    {
      textContent: "Makai Hurst\na.m.anim-59 (18)\nAccount settings",
      getAttribute: (name) => (name === "href" ? "https://www.ebay.com/usr/a.m.anim-59" : ""),
    },
  ];
  const context = {
    console,
    URL,
    window: {
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href: "https://www.ebay.com/itm/318496463400",
      hostname: "www.ebay.com",
      pathname: "/itm/318496463400",
      search: "",
      hash: "",
    },
    document: {
      body: { innerText: "Hi Makai!\nMakai Hurst\na.m.anim-59 (18)\nAccount settings" },
      querySelectorAll: () => accountElements,
    },
  };
  vm.createContext(context);
  vm.runInContext(`${source}; result = detectEbaySignedInUsernameFromPage();`, context);
  if (context.result !== "a.m.anim-59") {
    throw new Error(`Expected eBay username a.m.anim-59 instead of display name, got ${context.result}`);
  }

  const closedMenuContext = {
    console,
    URL,
    window: {
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href: "https://www.ebay.com/itm/318496463400",
      hostname: "www.ebay.com",
      pathname: "/itm/318496463400",
      search: "",
      hash: "",
    },
    document: {
      body: { innerText: "Hi Makai!\nSearch for anything\nWatchlist\nMy eBay" },
      querySelectorAll: () => [{ textContent: "Hi Makai!", getAttribute: () => "" }],
    },
  };
  vm.createContext(closedMenuContext);
  vm.runInContext(`${source}; result = detectEbaySignedInUsernameFromPage();`, closedMenuContext);
  if (closedMenuContext.result !== "") {
    throw new Error(`Expected closed eBay greeting to be ignored, got ${closedMenuContext.result}`);
  }

  const genericUserLabelContext = {
    console,
    URL,
    window: {
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href: "https://www.ebay.com/itm/5313646448913",
      hostname: "www.ebay.com",
      pathname: "/itm/5313646448913",
      search: "",
      hash: "",
    },
    document: {
      body: { innerText: "Product details\nStand\nShipping and returns" },
      querySelectorAll: () => [{
        id: "",
        textContent: "Stand",
        getAttribute: (name) => (name === "aria-label" ? "Stand" : ""),
      }],
    },
  };
  vm.createContext(genericUserLabelContext);
  vm.runInContext(`${source}; result = detectEbaySignedInUsernameFromPage();`, genericUserLabelContext);
  if (genericUserLabelContext.result !== "") {
    throw new Error(`Expected generic eBay page label Stand to be ignored, got ${genericUserLabelContext.result}`);
  }
  genericUserLabelContext.document.body.innerText = "Search results\n2000W\nSponsored";
  genericUserLabelContext.document.querySelectorAll = () => [{
    id: "",
    textContent: "2000W",
    getAttribute: (name) => name === "data-testid" ? "user-facing-model" : name === "aria-label" ? "2000W" : "",
  }];
  vm.runInContext(`result = detectEbaySignedInUsernameFromPage();`, genericUserLabelContext);
  if (genericUserLabelContext.result !== "") {
    throw new Error(`Expected generic product model 2000W to be ignored as a username, got ${genericUserLabelContext.result}`);
  }
  genericUserLabelContext.document.body.innerText = "Package weight\nkg\nItem details";
  genericUserLabelContext.document.querySelectorAll = () => [{
    id: "gh-ug",
    textContent: "kg",
    getAttribute: (name) => name === "id" ? "gh-ug" : name === "aria-label" ? "kg" : "",
  }];
  vm.runInContext(`result = detectEbaySignedInUsernameFromPage();`, genericUserLabelContext);
  if (genericUserLabelContext.result !== "") {
    throw new Error(`Expected eBay weight unit kg to be ignored as a username, got ${genericUserLabelContext.result}`);
  }

  const footerContext = {
    console,
    URL,
    window: {
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href: "https://www.ebay.com/sl/prelist/identify",
      hostname: "www.ebay.com",
      pathname: "/sl/prelist/identify",
      search: "",
      hash: "",
    },
    document: {
      body: { innerText: "Find a match\nCopyright © 1995-2026 eBay Inc. All Rights Reserved. Accessibility User Agreement Privacy Payments Terms of Use Cookies" },
      querySelectorAll: () => [],
    },
  };
  vm.createContext(footerContext);
  vm.runInContext(`${source}; result = detectEbaySignedInUsernameFromPage();`, footerContext);
  if (footerContext.result !== "") {
    throw new Error(`Expected eBay legal footer to be ignored, got ${footerContext.result}`);
  }
}

runEbayUsernameDetectionTest();

async function runEbayAccountFallbackTest() {
  const calls = [];
  const context = {
    console,
    URL,
    URLSearchParams,
    encodeURIComponent,
    API: "http://127.0.0.1:8000",
    fetch: async (url, options = {}) => {
      calls.push({ url: String(url), method: options.method || "GET", body: options.body || "" });
      if (String(url).includes("/ebay/browser-account?account_key=main-store")) {
        return { ok: true, json: async () => ({ can_list: true, detected_username: "a.m.anim-59" }) };
      }
      throw new Error(`Unexpected fetch ${url}`);
    },
    window: {
      __autozsEbayBrowserAccountReporterStarted: false,
      addEventListener: () => {},
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href: "https://www.ebay.com/sl/prelist/home?autozs_account_key=main-store",
      hostname: "www.ebay.com",
      pathname: "/sl/prelist/home",
      search: "?autozs_account_key=main-store",
      hash: "",
    },
    document: {
      hidden: false,
      addEventListener: () => {},
      body: { innerText: "Start listing with item info" },
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    setTimeout: (fn) => {
      fn();
      return 1;
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const result = await vm.runInContext('reportEbayBrowserAccount("main-store")', context);
  if (!result.can_list || result.detected_username !== "a.m.anim-59") {
    throw new Error(`Expected fallback account status, got ${JSON.stringify(result)}`);
  }
  if (calls.some((call) => call.method === "POST")) {
    throw new Error(`Expected no blank username POST, got ${JSON.stringify(calls)}`);
  }
}

async function runEbayMissingDraftVerificationTest() {
  const calls = [];
  const context = {
    console,
    URL,
    URLSearchParams,
    encodeURIComponent,
    API: "http://127.0.0.1:8000",
    fetch: async (url, options = {}) => {
      calls.push({ url: String(url), method: options.method || "GET", body: options.body || "" });
      if (String(url).includes("/listing-jobs/7/verify-draft")) {
        const body = JSON.parse(options.body || "{}");
        return { ok: true, json: async () => ({ id: 7, status: body.exists ? "saved_draft" : "tombstoned" }) };
      }
      if (String(url).includes("/ebay/browser-account")) {
        return { ok: true, json: async () => ({ can_list: true }) };
      }
      throw new Error(`Unexpected fetch ${url}`);
    },
    window: {
      __autozsEbayBrowserAccountReporterStarted: true,
      __autozsEbayDraftPresenceReporterStarted: true,
      addEventListener: () => {},
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href: "https://www.ebay.com/lstng?draftId=5121504565001&mode=AddItem&autozs_verify_draft=1&autozs_job_id=7",
      hostname: "www.ebay.com",
      pathname: "/lstng",
      search: "?draftId=5121504565001&mode=AddItem&autozs_verify_draft=1&autozs_job_id=7",
      hash: "",
    },
    document: {
      hidden: false,
      addEventListener: () => {},
      body: { innerText: "Listing not found. This listing is no longer available." },
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    setTimeout: (fn) => {
      fn();
      return 1;
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const result = await vm.runInContext("reportEbayDraftPresence()", context);
  if (result.status !== "tombstoned") {
    throw new Error(`Expected tombstoned draft verification result, got ${JSON.stringify(result)}`);
  }
  const verifyCall = calls.find((call) => call.url.includes("/listing-jobs/7/verify-draft"));
  if (!verifyCall) throw new Error(`Expected verify-draft POST, got ${JSON.stringify(calls)}`);
  const body = JSON.parse(verifyCall.body);
  if (body.exists !== false || body.ebay_draft_id !== "5121504565001") {
    throw new Error(`Expected missing draft payload, got ${verifyCall.body}`);
  }

  context.location.href = "https://www.ebay.com/lstng?draftId=5121504565001&mode=AddItem&autozs_reconcile_listing=1&autozs_job_id=7";
  context.location.search = "?draftId=5121504565001&mode=AddItem&autozs_reconcile_listing=1&autozs_job_id=7";
  context.document.body.innerText = "Complete your listing Photos Title Item specifics Pricing Shipping Save for later List it";
  const reconciled = await vm.runInContext("reportEbayDraftPresence()", context);
  if (reconciled.status !== "saved_draft") {
    throw new Error(`Expected an opened tracked draft to reconcile as saved_draft, got ${JSON.stringify(reconciled)}`);
  }
  const reconcileCall = calls.filter((call) => call.url.includes("/listing-jobs/7/verify-draft")).at(-1);
  const reconcileBody = JSON.parse(reconcileCall.body);
  if (reconcileBody.exists !== true || !reconcileBody.message.includes("reconciled eBay draft")) {
    throw new Error(`Expected existing-draft reconciliation payload, got ${reconcileCall.body}`);
  }
}

async function runEbayDraftListBulkVerificationTest() {
  const calls = [];
  const checks = [
    { job_id: 7, draft_id: "5121504565001", title: "F3 Stabilizer Knee Pads with Memory Foam" },
    { job_id: 8, draft_id: "5119188703400", title: "7350 4 Gal. Flooring Adhesive" },
  ];
  const context = {
    console,
    URL,
    URLSearchParams,
    encodeURIComponent,
    API: "http://127.0.0.1:8000",
    fetch: async (url, options = {}) => {
      calls.push({ url: String(url), method: options.method || "GET", body: options.body || "" });
      if (String(url).includes("/listing-jobs/")) {
        return { ok: true, json: async () => ({ status: "tombstoned" }) };
      }
      if (String(url).includes("/ebay/browser-account")) {
        return { ok: true, json: async () => ({ can_list: true }) };
      }
      throw new Error(`Unexpected fetch ${url}`);
    },
    window: {
      __autozsEbayBrowserAccountReporterStarted: true,
      __autozsEbayDraftPresenceReporterStarted: true,
      addEventListener: () => {},
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href: `https://www.ebay.com/sh/lst/drafts#autozs_verify_drafts=1&autozs_checks=${encodeURIComponent(JSON.stringify(checks))}`,
      hostname: "www.ebay.com",
      pathname: "/sh/lst/drafts",
      search: "",
      hash: `#autozs_verify_drafts=1&autozs_checks=${encodeURIComponent(JSON.stringify(checks))}`,
    },
    document: {
      hidden: false,
      addEventListener: () => {},
      body: { innerText: "Manage drafts Results:0 Looks like you don't have any drafts." },
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    setTimeout: (fn) => {
      fn();
      return 1;
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const result = await vm.runInContext("reportEbayDraftListPresence()", context);
  if (result.length !== 2 || result.some((item) => item.exists !== false)) {
    throw new Error(`Expected all draft list checks missing, got ${JSON.stringify(result)}`);
  }
  const verifyCalls = calls.filter((call) => call.url.includes("/verify-draft"));
  if (verifyCalls.length !== 2) throw new Error(`Expected two verify-draft calls, got ${JSON.stringify(calls)}`);
  verifyCalls.forEach((call) => {
    const body = JSON.parse(call.body);
    if (body.exists !== false || !body.message.includes("zero saved drafts")) {
      throw new Error(`Expected tombstone payload from empty drafts list, got ${call.body}`);
    }
  });
}

// Amazon capture: Depop reuses only the PRIMARY image, so capture must return
// exactly one image URL even when the page exposes a full gallery, and must
// collapse the SEO/referral URL to canonical /dp/<ASIN>.
function runAmazonCapture() {
  const gallery = {
    "https://m.media-amazon.com/images/I/hero._AC_SX679_.jpg": [679, 679],
    "https://m.media-amazon.com/images/I/hero._AC_SX466_.jpg": [466, 466],
  };
  const context = {
    console,
    URL,
    window: { matchMedia: () => ({ matches: false }) },
    location: {
      href: "https://www.amazon.com/Some-Long-Slug/dp/B08N5WRWNW/ref=sr_1_3?crid=XYZ&sr=8-3",
      hostname: "www.amazon.com",
      pathname: "/Some-Long-Slug/dp/B08N5WRWNW/ref=sr_1_3",
    },
    document: {
      title: "Amazon.com: Widget",
      body: { innerText: "Widget detail page" },
      documentElement: { innerHTML: "" },
      images: [],
      querySelector: (selector) => {
        if (selector === "#productTitle") return { innerText: "  Stainless Widget  " };
        if (/landingImage/.test(selector)) {
          return {
            getAttribute: (name) => (name === "data-a-dynamic-image" ? JSON.stringify(gallery) : null),
            src: "https://m.media-amazon.com/images/I/hero._AC_SX466_.jpg",
          };
        }
        return null;
      },
      querySelectorAll: (selector) => {
        if (/feature-bullets/.test(selector)) {
          return [{ innerText: "Rustproof" }, { innerText: "See more" }];
        }
        return [];
      },
    },
  };
  vm.createContext(context);
  vm.runInContext(`${source}; result = captureSourceProductFromPage();`, context);
  return context.result;
}

const amazon = runAmazonCapture();
if (amazon.source_url !== "https://www.amazon.com/dp/B08N5WRWNW") {
  throw new Error(`Expected canonical Amazon /dp/ URL, got ${amazon.source_url}`);
}
if (amazon.supplier_sku !== "B08N5WRWNW") {
  throw new Error(`Expected ASIN as supplier_sku, got ${amazon.supplier_sku}`);
}
if (amazon.title !== "Stainless Widget") {
  throw new Error(`Expected trimmed Amazon title, got ${JSON.stringify(amazon.title)}`);
}
if (amazon.image_urls.split("\n").filter(Boolean).length !== 1) {
  throw new Error(`Expected exactly one Amazon image, got ${JSON.stringify(amazon.image_urls)}`);
}
if (amazon.image_urls !== "https://m.media-amazon.com/images/I/hero.jpg") {
  throw new Error(`Expected full-resolution primary image, got ${amazon.image_urls}`);
}
if (!amazon.capture_debug || amazon.capture_debug.primary_image_only !== true) {
  throw new Error("Expected capture_debug to record primary_image_only.");
}
if (amazon.description !== "Rustproof") {
  throw new Error(`Expected 'See more' filtered from bullets, got ${JSON.stringify(amazon.description)}`);
}

// One Amazon parent listing fans out into a Depop listing per sibling variation,
// plus the customer review photos. Both ride along on depop_amazon.
function runAmazonVariationCapture() {
  const imageBlock = {
    parentAsin: "B0PARENT01",
    colorToAsin: { Black: { asin: "B0BLACK001" }, "Lake Blue": { asin: "B0BLUE0001" } },
    colorImages: {
      // The synthetic "initial" bucket is not a real variation and must be skipped.
      initial: [{ hiRes: "https://m.media-amazon.com/images/I/initial._AC_SL1500_.jpg" }],
      Black: [
        { hiRes: "https://m.media-amazon.com/images/I/black._AC_SL1500_.jpg", thumb: "https://m.media-amazon.com/images/I/black._AC_US40_.jpg" },
        { hiRes: "https://m.media-amazon.com/images/I/black2._AC_SL1500_.jpg" },
      ],
      "Lake Blue": [{ large: "https://m.media-amazon.com/images/I/blue._AC_SL1500_.jpg" }],
    },
  };
  const reviewNode = (src) => ({ getAttribute: (name) => (name === "src" ? src : null) });
  const reviewNodes = [
    reviewNode("https://m.media-amazon.com/images/I/rev1._AC_UC154,154_QL85_.jpg?aicid=community-reviews"),
    // Same photo at a different rendered size -> must dedupe to one entry.
    reviewNode("https://m.media-amazon.com/images/I/rev1._AC_UC300,300_QL85_.jpg?aicid=community-reviews"),
    reviewNode("https://m.media-amazon.com/images/I/rev2._AC_UC154,154_QL85_.jpg?aicid=community-reviews"),
    // Seller gallery / UI sprite on the same CDN, no review marker -> excluded.
    reviewNode("https://m.media-amazon.com/images/I/sprite._AC_SX679_.jpg"),
  ];
  // Carousel thumbnails. data-asin is the VIEWED variation (Black here) for every
  // photo regardless of what the reviewer bought, so only data-reviewid may be
  // used to attribute a photo.
  const carouselButtons = [
    { dataset: { url: "https://m.media-amazon.com/images/I/rev1._AC_UC154,154_.jpg", reviewid: "RREV1", asin: "B0BLACK001" } },
    { dataset: { url: "https://m.media-amazon.com/images/I/rev2._AC_UC154,154_.jpg", reviewid: "RREV2", asin: "B0BLACK001" } },
  ];
  // Only RREV1's body is rendered on the product page; RREV2's is not, so that
  // photo must stay unattributed rather than fall back to data-asin.
  const reviewBodies = [
    {
      id: "RREV1",
      querySelector: (selector) =>
        /format-strip/.test(selector) ? { textContent: "Color: Lake Blue, Style: Standard" } : null,
    },
  ];
  const context = {
    console,
    URL,
    window: { matchMedia: () => ({ matches: false }) },
    location: {
      href: "https://www.amazon.com/Bag/dp/B0BLACK001",
      hostname: "www.amazon.com",
      pathname: "/Bag/dp/B0BLACK001",
    },
    document: {
      title: "Amazon.com: Bag",
      body: { innerText: "Bag detail page" },
      documentElement: { innerHTML: "" },
      images: [],
      scripts: [{ textContent: `var obj = jQuery.parseJSON('${JSON.stringify(imageBlock)}');` }],
      querySelector: (selector) => {
        if (selector === "#productTitle") return { innerText: "Vegan Leather Bag" };
        return null;
      },
      querySelectorAll: (selector) => {
        if (/button\[data-reviewid\]/.test(selector)) return carouselButtons;
        if (selector === '[data-hook="review"]') return reviewBodies;
        if (/community|cm_cr_carousel|reviewsMedley|review-image-tile/.test(selector)) return reviewNodes;
        return [];
      },
    },
  };
  vm.createContext(context);
  vm.runInContext(`${source}; result = captureSourceProductFromPage();`, context);
  return context.result;
}

const amazonVariants = runAmazonVariationCapture();
const depopExtras = amazonVariants.depop_amazon;
if (!depopExtras) throw new Error("Expected depop_amazon on the Amazon capture payload.");
if (depopExtras.parent_asin !== "B0PARENT01") {
  throw new Error(`Expected parent ASIN, got ${depopExtras.parent_asin}`);
}
if (depopExtras.variations.length !== 2) {
  throw new Error(`Expected 2 variations with "initial" skipped, got ${JSON.stringify(depopExtras.variations)}`);
}
const blackVariation = depopExtras.variations.find((item) => item.label === "Black");
if (!blackVariation || blackVariation.asin !== "B0BLACK001") {
  throw new Error(`Expected Black mapped to its child ASIN, got ${JSON.stringify(blackVariation)}`);
}
if (blackVariation.image_url !== "https://m.media-amazon.com/images/I/black.jpg") {
  throw new Error(`Expected the first image at full resolution, got ${blackVariation.image_url}`);
}
if (depopExtras.review_photos.length !== 2) {
  throw new Error(
    `Expected 2 deduped review photos with non-review images excluded, got ${JSON.stringify(depopExtras.review_photos)}`
  );
}
if (depopExtras.review_photos[0].image_url !== "https://m.media-amazon.com/images/I/rev1.jpg") {
  throw new Error(`Expected the review photo upscaled to the original, got ${depopExtras.review_photos[0].image_url}`);
}
// Each photo must carry the review it came from -- the only trustworthy key.
if (depopExtras.review_photos[0].review_id !== "RREV1" || depopExtras.review_photos[1].review_id !== "RREV2") {
  throw new Error(`Expected review ids on the photos, got ${JSON.stringify(depopExtras.review_photos)}`);
}
// The colour map covers only the review body the page rendered, so RREV2 stays
// unresolved instead of being mislabelled from the viewed variation's ASIN.
if (depopExtras.review_colors.RREV1 !== "Lake Blue") {
  throw new Error(`Expected RREV1 mapped to its reviewer's colour, got ${JSON.stringify(depopExtras.review_colors)}`);
}
if ("RREV2" in depopExtras.review_colors) {
  throw new Error("RREV2 has no rendered review body and must not be given a colour.");
}
// The product record itself must still carry exactly one image.
if (amazonVariants.image_urls.split("\n").filter(Boolean).length > 1) {
  throw new Error("Variation capture must not add extra images to the product record.");
}


runEbayAccountFallbackTest()
  .then(runEbayMissingDraftVerificationTest)
  .then(runEbayDraftListBulkVerificationTest)
  .then(() => console.log("capture shipping, Amazon capture, eBay account fallback, and draft verification tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
