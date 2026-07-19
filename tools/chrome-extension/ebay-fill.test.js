const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/ebay-fill.js`, "utf8");

class FakeField {
  constructor({ id = "", name = "", placeholder = "", ariaLabel = "", tagName = "INPUT", parentText = "", type = "", contentEditable = false, visible = true } = {}) {
    this.id = id;
    this.name = name;
    this.placeholder = placeholder;
    this.tagName = tagName;
    this._value = "";
    this.textContent = "";
    this.innerText = "";
    this.isContentEditable = contentEditable;
    this.visible = visible;
    this.attributes = { "aria-label": ariaLabel, type };
    if (contentEditable) this.attributes.contenteditable = "true";
    this.parentElement = { innerText: parentText };
    this.events = [];
  }

  get value() {
    return this._prototypeValue || this._value || "";
  }

  set value(nextValue) {
    this._value = nextValue;
  }

  get innerHTML() {
    return this._html || "";
  }

  set innerHTML(value) {
    this._html = String(value || "");
    this.textContent = this._html.replace(/<[^>]+>/g, "");
    this.innerText = this.textContent;
  }

  dispatchEvent(event) {
    this.events.push(event.type);
  }

  focus() {
    this.focused = true;
  }

  getAttribute(key) {
    return Object.prototype.hasOwnProperty.call(this.attributes, key) ? this.attributes[key] : null;
  }

  hasAttribute(key) {
    return Object.prototype.hasOwnProperty.call(this.attributes, key);
  }

  setAttribute(key, value) {
    this.attributes[key] = String(value);
    if (key === "value") this.value = value;
  }

  matches(selector) {
    if (selector === 'input[type="checkbox"]') {
      return this.tagName === "INPUT" && this.getAttribute("type") === "checkbox";
    }
    if (selector === 'input[type="radio"]') {
      return this.tagName === "INPUT" && this.getAttribute("type") === "radio";
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
    return this.visible ? { width: 120, height: 32 } : { width: 0, height: 0 };
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

  closest() {
    return null;
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
      rawDescription.visible = htmlModeCheckbox.checked;
    },
  };
  const rawDescription = new FakeField({
    id: "rawEditor",
    name: "description",
    tagName: "TEXTAREA",
    parentText: "HTML source code",
    visible: false,
  });
  htmlModeCheckbox.click = () => {
    htmlModeCheckbox.checked = !htmlModeCheckbox.checked;
    rawDescription.visible = htmlModeCheckbox.checked;
  };
  const prelistSearch = new FakeField({
    placeholder: "Enter brand, model, description, etc.",
    parentText: "Start listing with item info Describe your item",
  });
  let prelistMode = "search";
  const prelistSearchButton = new FakeButton("Search");
  prelistSearchButton.click = () => {
    prelistSearchButton.clicked = true;
    prelistMode = "match";
  };
  const continueWithoutMatchButton = new FakeButton("Continue without match");
  continueWithoutMatchButton.click = () => {
    continueWithoutMatchButton.clicked = true;
    prelistMode = "condition";
  };
  let rawDescriptionEnabled = true;
  let htmlModeControlEnabled = true;
  const selectedCondition = new FakeButton("Condition New");
  selectedCondition.getAttribute = (key) => key === "aria-selected" ? "true" : key === "aria-label" ? "Condition New" : "";

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
        if (selector === "label") return htmlModeControlEnabled ? [htmlModeLabel] : [];
        if (selector === 'input[type="checkbox"]') return htmlModeControlEnabled ? [htmlModeCheckbox] : [];
        if (selector === "button") return prelistMode === "match" ? [continueWithoutMatchButton] : [prelistSearchButton];
        if (selector === "button, a") return prelistMode === "match" ? [continueWithoutMatchButton] : [prelistSearchButton];
        if (selector === 'input[type="radio"], button, [role="button"], [role="radio"], [role="combobox"], label') return [selectedCondition];
        if (selector === 'input[type="radio"]:checked, [aria-checked="true"], [aria-selected="true"]') return [selectedCondition];
        if (selector === "[role='option'], [role='menuitem'], li") return [];
        if (selector === "input, textarea, [role='textbox']") return prelistMode === "search" ? [prelistSearch] : [];
        if (selector === "input, textarea, [contenteditable], [role='textbox']") {
          return context.location?.pathname === "/sl/prelist/home" && prelistMode === "search" ? [prelistSearch] : fields;
        }
        return fields;
      },
      querySelector: (selector) => {
        if (selector === 'textarea[name="description"][id*="rawEditor"], textarea[name="description"]') return rawDescriptionEnabled ? rawDescription : null;
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
  context.location.search = "?autozs_job_id=22";
  context.location.hash = "";
  vm.runInContext("readAutoWorkflowState = () => ({ jobId: '99' }); readSavedJobId = () => '88';", context);
  const reconciledJobId = vm.runInContext("currentWorkflowJobId()", context);
  if (reconciledJobId !== "22") {
    throw new Error(`Expected reconciliation URL job id to override stale browser state, got ${reconciledJobId}`);
  }
  context.location.search = "";
  vm.runInContext("readAutoWorkflowState = () => null; readSavedJobId = () => '';", context);

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
  if (vm.runInContext("Boolean(findDescriptionSourceField())", context)) {
    throw new Error("Expected hidden raw description source to be ignored before HTML mode is enabled.");
  }
  const result = await vm.runInContext(`fillEbayListingDraft(${JSON.stringify(packageData)})`, context);

  const values = fields.map((field) => field._prototypeValue || field.value || field.textContent);
  if (result.filled !== 8 || result.total !== 8) {
    throw new Error(`Expected all field groups to fill, got ${JSON.stringify(result)}`);
  }
  if (!values.includes(packageData.title)) throw new Error("Expected title field to be filled.");
  if (!values.includes("21.49")) throw new Error("Expected price field to be filled.");
  if (!values.includes(packageData.sku)) throw new Error("Expected SKU field to be filled.");
  if (!values.includes("3")) throw new Error("Expected quantity field to be filled.");
  if (rawDescription.value !== packageData.description) {
    throw new Error(`Expected raw HTML description to be replaced exactly, got ${JSON.stringify(rawDescription.value)}`);
  }
  if (!htmlModeCheckbox.checked) {
    throw new Error("Expected HTML mode checkbox to be enabled before filling hidden raw description source.");
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
  const overlayFocusedField = new FakeField({ id: "autozs-overlay", parentText: "AutoZS loading overlay" });
  const guardedBrandField = new FakeField({ id: "guarded-brand", parentText: "Brand" });
  let nativeReplaceCalls = 0;
  context.document.activeElement = overlayFocusedField;
  context.chrome = {
    runtime: {
      sendMessage: (payload, callback) => {
        if (payload.action === "replace-text") nativeReplaceCalls += 1;
        callback({ ok: true });
      },
    },
  };
  context.__guardedBrandField = guardedBrandField;
  const guardedBrandFilled = await vm.runInContext(`setEbayTextFieldValue(__guardedBrandField, "Guarded Brand")`, context);
  if (!guardedBrandFilled || guardedBrandField.value !== "Guarded Brand") {
    throw new Error("Expected guarded Brand fallback to fill synthetically when focus is owned by another element.");
  }
  if (nativeReplaceCalls !== 0) {
    throw new Error("Expected native replace-text to be skipped when the focused element is not the target Brand field.");
  }
  delete context.chrome;
  delete context.document.activeElement;
  if (!result.lines.every((line) => !/publish|submit|list item/i.test(line))) {
    throw new Error("Fill results should not claim to publish or submit.");
  }
  const deceptiveUpcField = new FakeField({
    id: "universal-product-code",
    name: "universalProductCode",
    parentText: "Universal product code Description Show HTML Code",
  });
  fields.push(deceptiveUpcField);
  rawDescriptionEnabled = false;
  const safeDescriptionSource = vm.runInContext("findDescriptionSourceField()", context);
  if (safeDescriptionSource?.element === deceptiveUpcField) {
    throw new Error("Expected the description source finder to reject a nearby UPC input.");
  }
  fields.pop();
  rawDescriptionEnabled = false;
  htmlModeControlEnabled = false;
  htmlModeCheckbox.checked = false;
  const richDescription = new FakeField({
    id: "rich-description",
    tagName: "DIV",
    parentText: "Item description",
    contentEditable: true,
  });
  fields[4] = richDescription;
  const richDescriptionHtml = "<section><h2>Formatted product description</h2><p>Installs quickly.</p><ul><li>Clean fit</li></ul></section>";
  const richDescriptionFilled = await vm.runInContext(`fillDescription(${JSON.stringify(richDescriptionHtml)})`, context);
  if (!richDescriptionFilled || richDescription.innerHTML !== richDescriptionHtml) {
    throw new Error(`Expected HTML description fallback to fill rich editor, got filled=${richDescriptionFilled} html=${JSON.stringify(richDescription.innerHTML)}`);
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
  const schedule = vm.runInContext(`parseListingSchedule("2026-07-01T15:00:00Z")`, context);
  if (schedule.usDate !== "07/01/2026" || schedule.time12 !== "8:00 AM" || schedule.time24 !== "08:00") {
    throw new Error(`Expected next Wednesday 8 AM schedule formatting, got ${JSON.stringify(schedule)}`);
  }
  const easternSchedule = vm.runInContext(`parseListingSchedule("2026-07-20T21:00:00Z")`, context);
  if (easternSchedule.usDate !== "07/20/2026" || easternSchedule.time12 !== "2:00 PM" || easternSchedule.time24 !== "14:00") {
    throw new Error(`Expected 5 PM Eastern to fill eBay as 2 PM Pacific, got ${JSON.stringify(easternSchedule)}`);
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
  const originalQuerySelector = context.document.querySelector;
  context.document.body.innerText = "Your listing has been scheduled M18 Battery ID-800241899128 View listing";
  context.document.querySelectorAll = (selector) => {
    if (selector === 'a[href*="/itm/"]') return [{ href: "https://www.ebay.com/itm/800241899128" }];
    return [];
  };
  const publishConfirmation = vm.runInContext("detectEbayPublishConfirmation()", context);
  if (publishConfirmation.listingId !== "800241899128" || publishConfirmation.status !== "scheduled") {
    throw new Error(`Expected scheduled listing confirmation, got ${JSON.stringify(publishConfirmation)}`);
  }
  if (vm.runInContext("isEbayListingEditorPage()", context)) {
    throw new Error("Expected an eBay publish confirmation page not to be treated as a listing editor.");
  }
  const reconciliationCalls = [];
  context.fetch = async (url, options = {}) => {
    reconciliationCalls.push({ url: String(url), body: options.body || "" });
    return { ok: true, json: async () => ({ ok: true }) };
  };
  context.updateListingJob = async (jobId, body) => context.fetch(`${context.API}/listing-jobs/${jobId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  context.location.search = "";
  context.location.hash = "";
  const originalGetElementById = context.document.getElementById;
  const confirmationOverlay = {
    removed: false,
    removeAttribute: () => {},
    remove() { this.removed = true; },
  };
  context.document.getElementById = (id) => id === "autozs-ebay-fill-assistant" ? confirmationOverlay : originalGetElementById(id);
  vm.runInContext("readAutoWorkflowState = () => ({ mode: 'create_draft', phase: 'opened', productId: '29', jobId: '26' }); readSavedProductId = () => '29'; readSavedJobId = () => '26';", context);
  await vm.runInContext("reportEbayPublishConfirmation()", context);
  if (!confirmationOverlay.removed) {
    throw new Error("Expected eBay confirmation to remove the blocking AutoZS progress overlay.");
  }
  if (reconciliationCalls.length) {
    throw new Error(`Expected an untracked stale confirmation page not to update product 29, got ${JSON.stringify(reconciliationCalls)}`);
  }
  context.document.body.innerText = "Your listing is now live M18 Battery ID-800241899128 View listing";
  const genericLiveConfirmation = vm.runInContext("detectEbayPublishConfirmation()", context);
  if (genericLiveConfirmation.status !== "listed") {
    throw new Error(`Expected eBay's generic live confirmation to initially parse as listed, got ${JSON.stringify(genericLiveConfirmation)}`);
  }
  context.location.search = "?draftId=5314800361713&mode=AddItem";
  context.fetch = async (url, options = {}) => {
    reconciliationCalls.push({ url: String(url), body: options.body || "" });
    if (String(url).includes("/listing-jobs?")) {
      return {
        ok: true,
        json: async () => ([{
          id: 26,
          product_id: 29,
          ebay_draft_id: "5314800361713",
          listing_schedule_at: "2099-07-21T20:40:00",
          status: "needs_review",
        }]),
      };
    }
    return { ok: true, json: async () => ({ ok: true }) };
  };
  await vm.runInContext("reportEbayPublishConfirmation()", context);
  const recoveredJobCall = reconciliationCalls.find((call) => call.url.endsWith("/listing-jobs/26"));
  if (!recoveredJobCall) {
    throw new Error(`Expected stripped reconciliation parameters to recover through the matching draft ID, got ${JSON.stringify(reconciliationCalls)}`);
  }
  const recoveredListingCall = reconciliationCalls.find((call) => call.url.endsWith("/products/29/mark-listed"));
  const recoveredListingBody = JSON.parse(recoveredListingCall?.body || "{}");
  if (recoveredListingBody.status !== "scheduled") {
    throw new Error(`Expected a future planned start to override eBay's generic live wording, got ${recoveredListingCall?.body}`);
  }
  const recoveredJobBody = JSON.parse(recoveredJobCall.body);
  if (
    recoveredJobBody.status !== "completed" ||
    recoveredJobBody.listing_id !== "800241899128" ||
    !recoveredJobBody.message.includes("Recovered from matching eBay draft confirmation")
  ) {
    throw new Error(`Expected matching-draft recovery to complete the job, got ${recoveredJobCall.body}`);
  }
  context.location.search = "?autozs_reconcile_listing=1&autozs_product_id=34&autozs_job_id=22&autozs_account_key=main-store";
  context.location.hash = "";
  vm.runInContext("readAutoWorkflowState = () => ({}); readSavedProductId = () => ''; readSavedJobId = () => ''; writeAutoWorkflowState = (value) => value;", context);
  await vm.runInContext("reportEbayPublishConfirmation()", context);
  const reconcileJobCall = reconciliationCalls.find((call) => call.url.endsWith("/listing-jobs/22"));
  if (!reconcileJobCall) {
    throw new Error(`Expected listing confirmation to reconcile job 22, got ${JSON.stringify(reconciliationCalls)}`);
  }
  const reconcileJobBody = JSON.parse(reconcileJobCall.body);
  if (
    reconcileJobBody.status !== "completed" ||
    reconcileJobBody.listing_id !== "800241899128" ||
    !reconcileJobBody.message.includes("Reconciled from eBay confirmation")
  ) {
    throw new Error(`Expected completed reconciliation payload with listing id, got ${reconcileJobCall.body}`);
  }
  context.document.body.innerText = "Your listing has been updated. Changes are live.";
  const revisionConfirmation = vm.runInContext("detectEbayRevisionConfirmation()", context);
  if (!revisionConfirmation) {
    throw new Error("Expected eBay revision confirmation to be detected.");
  }
  context.document.body.innerText = "Your changes were saved successfully.";
  context.document.title = "Revise listing | eBay";
  const revisionDiagnostic = vm.runInContext("ebayRevisionConfirmationDiagnostic()", context);
  if (!revisionDiagnostic.includes("Your changes were saved successfully")) {
    throw new Error(`Expected revision diagnostic to preserve relevant status text, got ${revisionDiagnostic}`);
  }
  vm.runInContext(`readAutoWorkflowState = () => ({
    mode: "revise_price",
    revisionJobId: "91",
    phase: "confirmation_pending",
    targetPrice: "27.99"
  }); reportEbayRevisionConfirmation = async () => null;`, context);
  const pendingRevision = await vm.runInContext(`runPriceRevisionWorkflow(${JSON.stringify({ price: 27.99 })})`, context);
  if (!pendingRevision.message.includes("will not submit it again")) {
    throw new Error(`Expected pending revision to remain idempotent, got ${JSON.stringify(pendingRevision)}`);
  }
  context.document.querySelectorAll = originalQuerySelectorAll;

  const finalScheduleButton = new FakeButton("Schedule your listing");
  context.document.body.innerText = "Schedule your listing";
  context.document.querySelectorAll = (selector) => selector === "button, [role='button']" ? [finalScheduleButton] : [];
  const detectedFinalButton = vm.runInContext("findFinalScheduleButton()", context);
  if (detectedFinalButton !== finalScheduleButton) {
    throw new Error("Expected the exact final Schedule your listing button to be detected.");
  }
  vm.runInContext("parseListingSchedule = () => new Date(); findScheduleDayField = () => ({}); scheduleDateFieldMatches = () => true;", context);
  context.location.href = "https://www.ebay.com/lstng?draftId=123";
  context.document.querySelectorAll = (selector) => {
    if (selector === "button, [role='button']") return [finalScheduleButton];
    if (selector === 'a[href*="/itm/"]') return [];
    if (selector === '[role="alert"], [aria-live="assertive"], .error, [class*="error" i]') return [];
    return [];
  };
  const ignoredFinalClick = await vm.runInContext("submitScheduledListing({ listing_schedule_at: '2026-07-22T19:00:00' }, 20)", context);
  if (ignoredFinalClick.ok) {
    throw new Error(`Expected a no-op final List click not to be reported as submitted, got ${JSON.stringify(ignoredFinalClick)}`);
  }
  let finalButtonVisible = true;
  finalScheduleButton.clicked = false;
  finalScheduleButton.click = () => {
    finalScheduleButton.clicked = true;
    finalButtonVisible = false;
  };
  finalScheduleButton.getBoundingClientRect = () => finalButtonVisible ? { width: 120, height: 32 } : { width: 0, height: 0 };
  const acceptedFinalClick = await vm.runInContext("submitScheduledListing({ listing_schedule_at: '2026-07-22T19:00:00' }, 20)", context);
  if (!acceptedFinalClick.ok || !finalScheduleButton.clicked) {
    throw new Error(`Expected a responsive final List click to be reported as accepted, got ${JSON.stringify(acceptedFinalClick)}`);
  }
  const revisionSubmitButton = new FakeButton("Submit revisions");
  context.document.querySelectorAll = (selector) => {
    if (selector === "button, [role='button'], input[type='submit']") return [revisionSubmitButton];
    if (selector === '[role="alert"], [aria-live="assertive"], .error, [class*="error" i]') return [];
    return [];
  };
  context.document.body.innerText = "Review your listing changes";
  const revisionSubmitResult = await vm.runInContext("submitPriceRevision(27.99)", context);
  if (!revisionSubmitResult.ok || !revisionSubmitButton.clicked) {
    throw new Error(`Expected approved price revision to submit, got ${JSON.stringify(revisionSubmitResult)}`);
  }
  context.document.body.innerText = "Security check: verify your identity";
  const blockingIssue = vm.runInContext("detectEbaySubmissionIssue()", context);
  if (!blockingIssue) {
    throw new Error("Expected eBay identity verification to block automatic submission.");
  }
  context.document.body.innerText = "This looks like a duplicate listing. You can not have more than one fixed price listing of the same item at a time.";
  context.document.querySelectorAll = (selector) => selector === 'a[href*="/itm/"]'
    ? [{ href: "https://www.ebay.com/itm/800366194382" }]
    : [];
  const duplicateIssue = vm.runInContext("detectEbaySubmissionIssue()", context);
  if (!duplicateIssue || !duplicateIssue.includes("800366194382") || !duplicateIssue.includes("did not create another listing")) {
    throw new Error(`Expected eBay's duplicate-listing warning to block submission with its item id, got ${duplicateIssue}`);
  }
  context.document.body.innerText = "Looks like something is missing or invalid. Please fix any issues and try again. Condition, Item specifics";
  const validationIssue = vm.runInContext("detectEbaySubmissionIssue()", context);
  if (!validationIssue || !validationIssue.includes("Condition, Item specifics")) {
    throw new Error(`Expected eBay validation sections to be reported, got ${validationIssue}`);
  }
  if (vm.runInContext("requiredItemSpecificsSatisfied()", context)) {
    throw new Error("Expected eBay's generic Item specifics validation banner to fail final checks.");
  }
  const unrelatedNewControl = new FakeButton("Create new listing");
  context.__unrelatedNewControl = unrelatedNewControl;
  if (vm.runInContext(`conditionControlMatches({ element: __unrelatedNewControl, text: normalizeText("Create new listing") }, "new")`, context)) {
    throw new Error("Expected unrelated New controls not to be mistaken for the item condition.");
  }
  context.document.querySelectorAll = originalQuerySelectorAll;

  context.location.pathname = "/sl/prelist/home";
  context.document.body.innerText = "Start listing with item info Describe your item";
  const prelistResult = await vm.runInContext(`prepareEbayPrelist(${JSON.stringify(packageData)})`, context);
  if (!prelistResult.ok || !prelistSearchButton.clicked) {
    throw new Error(`Expected prelist search to be prepared and submitted, got ${JSON.stringify(prelistResult)}`);
  }
  if ((prelistSearch._prototypeValue || prelistSearch.value) !== packageData.title) {
    throw new Error(`Expected prelist search field to receive the listing title, got value=${JSON.stringify(prelistSearch._prototypeValue || prelistSearch.value)} result=${JSON.stringify(prelistResult)}`);
  }
  prelistMode = "match";
  context.document.body.innerText = "Find a match\nRelated listings from other sellers\nContinue without match";
  const matchResult = await vm.runInContext(`prepareEbayPrelist(${JSON.stringify(packageData)})`, context);
  if (!matchResult.ok || !continueWithoutMatchButton.clicked) {
    throw new Error(`Expected eBay match screen to continue without match, got ${JSON.stringify(matchResult)}`);
  }

  let categoryDialogOpen = false;
  const categoryOpener = new FakeButton("None selected");
  categoryOpener.getAttribute = (name) => name === "aria-label" ? "Selected category None selected - Edit category" : null;
  categoryOpener.click = () => {
    categoryOpener.clicked = true;
    categoryDialogOpen = true;
  };
  const flooringCategory = new FakeButton("Home & Garden > Home Improvement > Building & Hardware > Flooring & Tiles > Other Flooring & Tiles");
  const carpetCategory = new FakeButton("Home & Garden > Rugs & Carpets > Carpet Tiles");
  const vinylCategory = new FakeButton("Home & Garden > Home Improvement > Building & Hardware > Flooring & Tiles > Vinyl Flooring");
  const categoryDone = new FakeButton("Done");
  categoryDone.click = () => {
    categoryDone.clicked = true;
    categoryDialogOpen = false;
    context.document.body.innerText = "Confirm details\nCondition\nNew";
  };
  const categoryDialog = {
    innerText: "Category\nSuggested\nHome & Garden > Rugs & Carpets > Carpet Tiles\nDone",
    textContent: "Category Suggested Home & Garden > Rugs & Carpets > Carpet Tiles Done",
    querySelectorAll: (selector) => selector === "button" ? [flooringCategory, carpetCategory, vinylCategory, categoryDone] : [],
  };
  context.document.body.innerText = "Provide a category for your item\nNone selected\nContinue without match";
  context.document.querySelector = (selector) => selector === '[role="dialog"]' && categoryDialogOpen ? categoryDialog : null;
  context.document.querySelectorAll = (selector) => selector === "button" || selector === "button, [role='button']" ? [categoryOpener] : [];
  const categoryResult = await vm.runInContext(`preparePrelistCategory(${JSON.stringify({ title: "Azure Edge Blue Commercial Carpet Tile" })})`, context);
  if (!categoryResult.ok || !categoryOpener.clicked || !carpetCategory.clicked || flooringCategory.clicked || vinylCategory.clicked || !categoryDone.clicked) {
    throw new Error(`Expected the Carpet Tiles suggestion to be selected and confirmed, got ${JSON.stringify(categoryResult)}`);
  }
  const batteryCategory = new FakeButton("Home & Garden > Tools & Workshop Equipment > Power Tool & Air Tool Accessories > Power Tool Batteries");
  const chargerCategory = new FakeButton("Home & Garden > Tools & Workshop Equipment > Power Tool & Air Tool Accessories > Power Tool Battery Chargers");
  context.__batteryCategory = batteryCategory;
  context.__chargerCategory = chargerCategory;
  const chargerContextTokens = await vm.runInContext(`prelistCategoryTokens(${JSON.stringify(
    "M12 and M18 Multi-Voltage Battery | FREE SHIPPING <p>Milwaukee multi-voltage battery charger</p> /power-tool-battery-chargers/"
  )})`, context);
  context.__chargerContextTokens = chargerContextTokens;
  const batteryScore = vm.runInContext("prelistCategoryScore(__batteryCategory, __chargerContextTokens)", context);
  const chargerScore = vm.runInContext("prelistCategoryScore(__chargerCategory, __chargerContextTokens)", context);
  if (chargerScore <= batteryScore) {
    throw new Error(`Expected full package context to prefer Battery Chargers (${chargerScore}) over Batteries (${batteryScore}).`);
  }

  const voltageLabelControl = new FakeButton("Voltage");
  voltageLabelControl.id = "item-specific-dropdown-label-1";
  voltageLabelControl.className = "tooltip__host";
  voltageLabelControl.getAttribute = () => "";
  const voltageValueControl = new FakeButton("");
  voltageValueControl.className = "se-expand-button__button fake-menu-button__button";
  voltageValueControl.getAttribute = (name) => name === "aria-label" ? "Voltage" : "";
  context.__voltageLabelControl = { element: voltageLabelControl, text: "attributes voltage" };
  context.__voltageValueControl = { element: voltageValueControl, text: "voltage" };
  const voltageLabelScore = vm.runInContext(`itemSpecificDropdownTriggerScore(__voltageLabelControl, "voltage")`, context);
  const voltageValueScore = vm.runInContext(`itemSpecificDropdownTriggerScore(__voltageValueControl, "voltage")`, context);
  if (voltageValueScore >= voltageLabelScore) {
    throw new Error(`Expected the Voltage value dropdown (${voltageValueScore}) to outrank its tooltip label (${voltageLabelScore}).`);
  }
  const inferredChargerSpecifics = vm.runInContext(`inferredItemSpecifics(${JSON.stringify({
    title: "M12 and M18 12-Volt/18-Volt Lithium-Ion Multi-Voltage Battery",
    description: "Milwaukee multi-voltage battery charger",
  })})`, context);
  if (inferredChargerSpecifics.Voltage !== "18 V") {
    throw new Error(`Expected multi-voltage inference to select 18 V, got ${JSON.stringify(inferredChargerSpecifics.Voltage)}.`);
  }
  if (inferredChargerSpecifics["Battery Included"] !== "No") {
    throw new Error(`Expected a charger listing to infer that no battery is included, got ${JSON.stringify(inferredChargerSpecifics["Battery Included"])}.`);
  }
  const inferredVacuumSpecifics = vm.runInContext(`inferredItemSpecifics(${JSON.stringify({
    title: "M18 FUEL PACKOUT 18-Volt Cordless 2.5 Gal. Wet/Dry",
    description: "Portable jobsite vacuum",
    source_url: "https://www.homedepot.com/p/example-Wet-Dry-Vacuum/123",
  })})`, context);
  if (inferredVacuumSpecifics.Type !== "Handheld") {
    throw new Error(`Expected the PACKOUT wet/dry vacuum to infer eBay Type Handheld, got ${JSON.stringify(inferredVacuumSpecifics.Type)}.`);
  }

  let conditionPopupOpen = false;
  let conditionSelected = false;
  const conditionOpener = new FakeButton("Condition Select");
  conditionOpener.click = () => {
    conditionPopupOpen = true;
  };
  const newConditionOption = new FakeButton("New");
  newConditionOption.click = () => {
    conditionSelected = true;
  };
  context.document.querySelectorAll = (selector) => {
    if (selector === 'input[type="radio"], button, [role="button"], [role="radio"], [role="combobox"], label') return [conditionOpener];
    if (selector === '[role="dialog"], [role="listbox"], [role="menu"], [data-testid*="condition" i]') {
      return conditionPopupOpen ? [{ querySelectorAll: () => [newConditionOption], getBoundingClientRect: () => ({ width: 240, height: 140 }) }] : [];
    }
    if (selector === 'input[type="radio"], button, [role="button"], [role="radio"], [role="option"], [role="menuitem"], label, li') {
      return conditionPopupOpen ? [newConditionOption] : [conditionOpener];
    }
    if (selector === 'input[type="radio"]:checked, [aria-checked="true"], [aria-selected="true"]') return conditionSelected ? [newConditionOption] : [];
    return [];
  };
  const popupConditionOk = await vm.runInContext(`chooseVisibleCondition("New")`, context);
  if (!popupConditionOk || !conditionPopupOpen || !conditionSelected) {
    throw new Error("Expected condition popup option New to be selected automatically.");
  }

  const directConditionRadio = new FakeField({ id: "condition-1000", name: "conditionId", type: "radio", visible: false });
  directConditionRadio.value = "1000";
  directConditionRadio.checked = false;
  directConditionRadio.click = () => { directConditionRadio.checked = true; };
  const directConditionLabel = {
    innerText: "New",
    textContent: "New",
    getBoundingClientRect: () => ({ width: 90, height: 32 }),
    click: () => { directConditionRadio.checked = true; },
  };
  context.__directConditionRadio = directConditionRadio;
  context.document.querySelectorAll = (selector) => {
    if (selector === 'input[type="radio"]') return [directConditionRadio];
    if (selector === 'input[type="radio"]:checked, [aria-checked="true"], [aria-selected="true"]') return directConditionRadio.checked ? [directConditionRadio] : [];
    return [];
  };
  context.document.querySelector = (selector) => selector === 'label[for="condition-1000"]' ? directConditionLabel : null;
  const directConditionOk = await vm.runInContext(`chooseVisibleCondition("New")`, context);
  if (!directConditionOk || !directConditionRadio.checked) {
    throw new Error("Expected eBay's current conditionId radio to be selected directly.");
  }

  const customBrandOption = new FakeButton("PLUMBFLEX");
  customBrandOption.getAttribute = (key) => key === "aria-label" ? "Add custom value PLUMBFLEX" : "";
  context.__customBrandOption = customBrandOption;
  if (!vm.runInContext(`itemSpecificOptionMatches(__customBrandOption, "PLUMBFLEX")`, context)) {
    throw new Error("Expected eBay's Add custom value Brand option to match the supplied brand.");
  }
  context.document.querySelectorAll = originalQuerySelectorAll;
  context.document.querySelector = originalQuerySelector;

  const oldDateField = new FakeField({ id: "schedule-start-date", parentText: "Schedule start date" });
  oldDateField.value = "7/1/2026";
  const newDateField = new FakeField({ id: "schedule-start-date", parentText: "Schedule start date" });
  newDateField.value = "7/9/2026";
  const calendarToggle = new FakeButton("Calendar");
  const calendarTarget = new FakeButton("9");
  context.__oldDateField = oldDateField;
  context.__newDateField = newDateField;
  context.__calendarToggle = calendarToggle;
  context.__calendarTarget = calendarTarget;
  context.__currentScheduleDateField = oldDateField;
  const requeryDateOk = await vm.runInContext(`
    (async () => {
      const schedule = parseListingSchedule("2026-07-09T15:35:00");
      findScheduleCalendarToggle = () => __calendarToggle;
      findScheduleCalendarDay = () => __calendarTarget;
      findScheduleCalendarNextMonth = () => null;
      findScheduleDayField = () => __currentScheduleDateField;
      __calendarTarget.click = () => { __currentScheduleDateField = __newDateField; };
      return chooseScheduleCalendarDate(__oldDateField, schedule);
    })()
  `, context);
  if (!requeryDateOk) {
    throw new Error("Expected schedule calendar selection to verify against the re-rendered date field.");
  }
  const stableScheduleOk = await vm.runInContext(`
    (async () => {
      let reapplied = false;
      let dateValue = "7/18/2026";
      let timeMatches = false;
      findScheduleDayField = () => ({ value: dateValue });
      scheduleTimeMatches = () => timeMatches;
      applyListingSchedule = async () => {
        reapplied = true;
        dateValue = "7/24/2026";
        timeMatches = true;
        return true;
      };
      const ok = await ensureListingScheduleStable({ listing_schedule_at: "2026-07-24T19:00:00" });
      return { ok, reapplied };
    })()
  `, context);
  if (!stableScheduleOk.ok || !stableScheduleOk.reapplied) {
    throw new Error(`Expected a reset eBay schedule to be reapplied before submission, got ${JSON.stringify(stableScheduleOk)}`);
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
