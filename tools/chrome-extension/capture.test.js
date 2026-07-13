const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/capture.js`, "utf8");

function runCapture(visibleText, { offerPrice = "17.97", productName = "HDX 13 Gallon Reinforced Top Drawstring Fresh Scented Tall Kitchen Trash Bags 200 Count" } = {}) {
  const context = {
    console,
    URL,
    window: {
      matchMedia: () => ({ matches: false }),
    },
    location: {
      href: "https://www.homedepot.com/p/HDX-13-Gallon-Reinforced-Top-Drawstring-Fresh-Scented-Tall-Kitchen-Trash-Bags-with-20-PCR-200-Count-HDR13XHFN200W-F/331012931?ea_auto_import=1&auto_download_test=1&MERCH=REC",
      hostname: "www.homedepot.com",
      pathname: "/p/HDX-13-Gallon-Reinforced-Top-Drawstring-Fresh-Scented-Tall-Kitchen-Trash-Bags-with-20-PCR-200-Count-HDR13XHFN200W-F/331012931",
    },
    document: {
      body: { innerText: visibleText },
      documentElement: { innerHTML: "" },
      images: [],
      querySelector: () => null,
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
if (!freeShippingWithSubscription.source_url.includes("MERCH=REC")) {
  throw new Error(`Expected normal Home Depot params to remain, got ${freeShippingWithSubscription.source_url}`);
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
        return { ok: true, json: async () => ({ id: 7, status: "tombstoned" }) };
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

runEbayAccountFallbackTest()
  .then(runEbayMissingDraftVerificationTest)
  .then(runEbayDraftListBulkVerificationTest)
  .then(() => console.log("capture shipping, eBay account fallback, and draft verification tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
