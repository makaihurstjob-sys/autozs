const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/ebay-fill.js`, "utf8");

class FakeField {
  constructor({ id = "", name = "", placeholder = "", ariaLabel = "", tagName = "INPUT", parentText = "", type = "" } = {}) {
    this.id = id;
    this.name = name;
    this.placeholder = placeholder;
    this.tagName = tagName;
    this._value = "";
    this.textContent = "";
    this.innerText = "";
    this.attributes = { "aria-label": ariaLabel, type };
    this.parentElement = { innerText: parentText };
    this.events = [];
  }

  get value() {
    return this._prototypeValue || this._value || "";
  }

  set value(nextValue) {
    this._value = nextValue;
  }

  dispatchEvent(event) {
    this.events.push(event.type);
  }

  focus() {
    this.focused = true;
  }

  getAttribute(key) {
    return this.attributes[key] || "";
  }

  setAttribute(key, value) {
    this.attributes[key] = String(value);
    if (key === "value") this.value = value;
  }

  matches(selector) {
    if (selector === 'input[type="checkbox"]') {
      return this.tagName === "INPUT" && this.getAttribute("type") === "checkbox";
    }
    return false;
  }

  click() {
    if (this.getAttribute("type") === "checkbox") this.checked = !this.checked;
  }

  closest(selector) {
    if (selector === "label") return null;
    return this.parentElement;
  }

  getBoundingClientRect() {
    return { width: 120, height: 32 };
  }
}

class FakeButton {
  constructor(text = "Search") {
    this.innerText = text;
    this.textContent = text;
    this.clicked = false;
  }

  click() {
    this.clicked = true;
  }

  getBoundingClientRect() {
    return { width: 90, height: 32 };
  }

  getAttribute() {
    return "";
  }

  scrollIntoView() {}
}

async function runAssistantTest() {
  const fields = [
    new FakeField({ id: "listing-title", parentText: "Listing title" }),
    new FakeField({ name: "buyItNowPrice", parentText: "Buy It Now price" }),
    new FakeField({ placeholder: "Custom label SKU", parentText: "Custom label" }),
    new FakeField({ ariaLabel: "Quantity", parentText: "Available quantity" }),
    new FakeField({ id: "description-box", tagName: "TEXTAREA", parentText: "Item description" }),
    new FakeField({ id: "brand-specific", parentText: "Brand" }),
  ];
  const htmlModeCheckbox = new FakeField({
    id: "html-mode",
    tagName: "INPUT",
    type: "checkbox",
    parentText: "Show HTML Code",
  });
  htmlModeCheckbox.checked = false;
  const htmlModeLabel = {
    innerText: "Show HTML Code",
    textContent: "Show HTML Code",
    getAttribute: (key) => key === "for" ? "html-mode" : "",
    getBoundingClientRect: () => ({ width: 120, height: 24 }),
    click: () => {
      htmlModeCheckbox.checked = !htmlModeCheckbox.checked;
    },
  };
  const rawDescription = new FakeField({
    id: "rawEditor",
    name: "description",
    tagName: "TEXTAREA",
    parentText: "HTML source code",
  });
  const prelistSearch = new FakeField({
    placeholder: "Enter brand, model, description, etc.",
    parentText: "Start listing with item info Describe your item",
  });
  const prelistSearchButton = new FakeButton("Search");
  const continueWithoutMatchButton = new FakeButton("Continue without match");
  let prelistMode = "search";

  const context = {
    console,
    setTimeout,
    setInterval,
    clearInterval,
    API: "http://127.0.0.1:8000",
    URLSearchParams,
    window: { __autozsEbayFillAssistant: false, CSS: { escape: (value) => String(value) }, scrollTo: () => {} },
    CSS: { escape: (value) => String(value) },
    location: { search: "" },
    document: {
      body: { scrollHeight: 1000, scrollTop: 0 },
      documentElement: { scrollHeight: 1000, scrollTop: 0 },
      createElement: () => {
        const element = { _html: "", innerText: "", textContent: "" };
        Object.defineProperty(element, "innerHTML", {
          get() {
            return this._html;
          },
          set(value) {
            this._html = String(value || "");
            this.textContent = this._html.replace(/<[^>]+>/g, "");
            this.innerText = this.textContent;
          },
        });
        return element;
      },
      querySelectorAll: (selector) => {
        if (selector === 'input[type="file"]') return [];
        if (selector === "label") return [htmlModeLabel];
        if (selector === 'input[type="checkbox"]') return [htmlModeCheckbox];
        if (selector === "button") return prelistMode === "match" ? [continueWithoutMatchButton] : [prelistSearchButton];
        if (selector === "button, a") return prelistMode === "match" ? [continueWithoutMatchButton] : [prelistSearchButton];
        if (selector === "input, textarea, [role='textbox']") return prelistMode === "search" ? [prelistSearch] : [];
        return fields;
      },
      querySelector: (selector) => {
        if (selector === 'textarea[name="description"][id*="rawEditor"], textarea[name="description"]') return rawDescription;
        if (selector === `label[for="html-mode"]`) return htmlModeLabel;
        return null;
      },
      getElementById: (id) => id === "html-mode" ? htmlModeCheckbox : null,
      dispatchEvent: () => true,
    },
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    InputEvent: class {
      constructor(type) {
        this.type = type;
      }
    },
    Event: class {
      constructor(type) {
        this.type = type;
      }
    },
    KeyboardEvent: class {
      constructor(type) {
        this.type = type;
      }
    },
    HTMLInputElement: class {},
    HTMLTextAreaElement: class {},
    stripListingHtml: (value) => String(value).replace(/<[^>]+>/g, "").trim(),
  };
  Object.defineProperty(context.HTMLInputElement.prototype, "value", {
    set(value) {
      this._prototypeValue = value;
    },
  });
  Object.defineProperty(context.HTMLTextAreaElement.prototype, "value", {
    set(value) {
      this._prototypeValue = value;
    },
  });

  vm.createContext(context);
  vm.runInContext(source, context);

  context.location.search = "";
  context.location.hash = "#autozs_fill=1&autozs_product_id=40";
  const hashProductId = vm.runInContext("readAutozsParams().get('autozs_product_id')", context);
  if (hashProductId !== "40") {
    throw new Error(`Expected product id from hash fallback, got ${hashProductId}`);
  }
  context.location.hash = "#autozs_fill=1&autozs_product_id=40&autozs_job_id=99";
  const hashJobId = vm.runInContext("readAutozsParams().get('autozs_job_id')", context);
  if (hashJobId !== "99") {
    throw new Error(`Expected job id from hash fallback, got ${hashJobId}`);
  }
  context.location.hash = "#autozs_fill=1&autozs_product_id=40&autozs_autosubmit=1";
  const hashAutoSubmit = vm.runInContext("readAutozsParams().get('autozs_autosubmit')", context);
  if (hashAutoSubmit !== "1") {
    throw new Error(`Expected guarded auto-submit flag from hash fallback, got ${hashAutoSubmit}`);
  }

  context.location.hostname = "www.ebay.com";
  context.location.pathname = "/lstng";
  const isListingEditor = vm.runInContext("isEbayListingEditorPage()", context);
  if (!isListingEditor) {
    throw new Error("Expected /lstng to be detected as an eBay listing editor page.");
  }
  context.location.pathname = "/sl/list";
  const isSellListingEditor = vm.runInContext("isEbayListingEditorPage()", context);
  if (!isSellListingEditor) {
    throw new Error("Expected /sl/list to be detected as an eBay listing editor page.");
  }
  context.location.pathname = "/sl/prelist/home";
  const isPrelist = vm.runInContext("isEbayPrelistPage()", context);
  const isPrelistEditor = vm.runInContext("isEbayListingEditorPage()", context);
  if (!isPrelist || isPrelistEditor) {
    throw new Error("Expected /sl/prelist/home to be detected as prelist but not listing editor.");
  }
  context.location.pathname = "/sl/prelist/identify";
  const isIdentifyPrelist = vm.runInContext("isEbayPrelistPage()", context);
  if (!isIdentifyPrelist) {
    throw new Error("Expected /sl/prelist/identify to be detected as prelist.");
  }
  context.location.pathname = "/itm/317691488342";
  if (vm.runInContext("isEbayListingEditorPage() || isEbayPrelistPage()", context)) {
    throw new Error("Expected regular eBay item pages to keep the Listing Assistant hidden.");
  }
  context.location.pathname = "/sch/i.html";
  if (vm.runInContext("isEbayListingEditorPage() || isEbayPrelistPage()", context)) {
    throw new Error("Expected eBay search pages to keep the Listing Assistant hidden.");
  }

  const packageData = {
    title: "HDX 13 Gallon Trash Bags",
    price: 21.49,
    sku: "HDR13XHFN200W-F",
    quantity: 3,
    description: "<p>Fresh scented tall kitchen trash bags.</p>",
    item_specifics: { Brand: "HDX" },
  };
  const result = await vm.runInContext(`fillEbayListingDraft(${JSON.stringify(packageData)})`, context);

  const values = fields.map((field) => field._prototypeValue || field.value || field.textContent);
  if (result.filled !== 7 || result.total !== 7) {
    throw new Error(`Expected all field groups to fill, got ${JSON.stringify(result)}`);
  }
  if (!values.includes(packageData.title)) throw new Error("Expected title field to be filled.");
  if (!values.includes("21.49")) throw new Error("Expected price field to be filled.");
  if (!values.includes(packageData.sku)) throw new Error("Expected SKU field to be filled.");
  if (!values.includes("3")) throw new Error("Expected quantity field to be filled.");
  if (rawDescription.value !== packageData.description) {
    throw new Error(`Expected raw HTML description to be replaced exactly, got ${JSON.stringify(rawDescription.value)}`);
  }
  rawDescription._prototypeValue = `old plain text ${packageData.description}`;
  const exactDescriptionMatch = vm.runInContext(
    `descriptionSourceExactlyMatches({ value: ${JSON.stringify(rawDescription.value)} }, ${JSON.stringify(packageData.description)})`,
    context
  );
  if (exactDescriptionMatch) {
    throw new Error("Expected appended HTML after old text to fail exact source verification.");
  }
  if (!values.includes("HDX")) throw new Error("Expected provided brand item specific to be filled.");
  if (!result.lines.every((line) => !/publish|submit|list item/i.test(line))) {
    throw new Error("Fill results should not claim to publish or submit.");
  }
  const formattedFallbackDescription = vm.runInContext(
    `listingDescriptionPlainText('<div>Anim59 Home Improvement</div><div>Fast shipping</div><h1>Prime-Line Sash Balance</h1>')`,
    context
  );
  if (
    !/Improvement\s*\n+\s*Fast shipping/.test(formattedFallbackDescription) ||
    !/Fast shipping\s*\n+\s*Prime-Line/.test(formattedFallbackDescription)
  ) {
    throw new Error(`Expected HTML description fallback to preserve line breaks, got ${JSON.stringify(formattedFallbackDescription)}`);
  }
  const schedule = vm.runInContext(`parseListingSchedule("2026-07-01T08:00:00")`, context);
  if (schedule.usDate !== "07/01/2026" || schedule.time12 !== "8:00 AM" || schedule.time24 !== "08:00") {
    throw new Error(`Expected next Wednesday 8 AM schedule formatting, got ${JSON.stringify(schedule)}`);
  }
  const doubledTitleMatch = vm.runInContext(
    `fieldValueMatchesExactly({ tagName: "INPUT", value: "1313 Gallon Reinforced Top Drawstring Fresh Scented Tall Kitchen | FREE SHIPPING" }, "13 Gallon Reinforced Top Drawstring Fresh Scented Tall Kitchen | FREE SHIPPING")`,
    context
  );
  if (doubledTitleMatch) {
    throw new Error("Expected doubled eBay title prefix to fail exact title verification.");
  }
  const formattedPriceMatch = vm.runInContext(`fieldValueMatchesExactly({ tagName: "INPUT", value: "$25.99" }, "25.99")`, context);
  if (!formattedPriceMatch) {
    throw new Error("Expected formatted eBay price to pass exact numeric verification.");
  }
  context.location.pathname = "/lstng";
  const revisionResult = await vm.runInContext(`runPriceRevisionWorkflow(${JSON.stringify({ price: 27.99 })})`, context);
  if (!revisionResult.lines.includes("OK price $27.99")) {
    throw new Error(`Expected revision workflow to fill only the price, got ${JSON.stringify(revisionResult)}`);
  }

  const originalQuerySelectorAll = context.document.querySelectorAll;
  context.document.body.innerText = "Your listing has been scheduled M18 Battery ID-800241899128 View listing";
  context.document.querySelectorAll = (selector) => {
    if (selector === 'a[href*="/itm/"]') return [{ href: "https://www.ebay.com/itm/800241899128" }];
    return [];
  };
  const publishConfirmation = vm.runInContext("detectEbayPublishConfirmation()", context);
  if (publishConfirmation.listingId !== "800241899128" || publishConfirmation.status !== "scheduled") {
    throw new Error(`Expected scheduled listing confirmation, got ${JSON.stringify(publishConfirmation)}`);
  }
  context.document.body.innerText = "Your listing has been updated. Changes are live.";
  const revisionConfirmation = vm.runInContext("detectEbayRevisionConfirmation()", context);
  if (!revisionConfirmation) {
    throw new Error("Expected eBay revision confirmation to be detected.");
  }
  context.document.querySelectorAll = originalQuerySelectorAll;

  const finalScheduleButton = new FakeButton("Schedule your listing");
  context.document.body.innerText = "Schedule your listing";
  context.document.querySelectorAll = (selector) => selector === "button, [role='button']" ? [finalScheduleButton] : [];
  const detectedFinalButton = vm.runInContext("findFinalScheduleButton()", context);
  if (detectedFinalButton !== finalScheduleButton) {
    throw new Error("Expected the exact final Schedule your listing button to be detected.");
  }
  context.document.body.innerText = "Security check: verify your identity";
  const blockingIssue = vm.runInContext("detectEbaySubmissionIssue()", context);
  if (!blockingIssue) {
    throw new Error("Expected eBay identity verification to block automatic submission.");
  }
  context.document.querySelectorAll = originalQuerySelectorAll;

  const prelistResult = await vm.runInContext(`prepareEbayPrelist(${JSON.stringify(packageData)})`, context);
  if (!prelistResult.ok || !prelistSearchButton.clicked) {
    throw new Error(`Expected prelist search to be prepared and submitted, got ${JSON.stringify(prelistResult)}`);
  }
  if ((prelistSearch._prototypeValue || prelistSearch.value) !== packageData.title) {
    throw new Error("Expected prelist search field to receive the listing title.");
  }
  prelistMode = "match";
  context.document.body.innerText = "Find a match\nRelated listings from other sellers\nContinue without match";
  const matchResult = await vm.runInContext(`prepareEbayPrelist(${JSON.stringify(packageData)})`, context);
  if (!matchResult.ok || !continueWithoutMatchButton.clicked) {
    throw new Error(`Expected eBay match screen to continue without match, got ${JSON.stringify(matchResult)}`);
  }

  const apiImageUrl = vm.runInContext(`localPathToApiUrl("downloads/product_images/40/01.jpg")`, context);
  if (apiImageUrl !== "http://127.0.0.1:8000/downloads/product_images/40/01.jpg") {
    throw new Error(`Expected local image path to become API URL, got ${apiImageUrl}`);
  }

  const uploadResult = await vm.runInContext(
    `uploadListingImages(${JSON.stringify({ manual_image_paths: ["downloads/product_images/40/01.jpg"] })})`,
    context
  );
  if (uploadResult.ok || !uploadResult.message.includes("could not find eBay image file input")) {
    throw new Error(`Expected safe image upload failure, got ${JSON.stringify(uploadResult)}`);
  }
}

runAssistantTest()
  .then(() => console.log("ebay fill assistant tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
