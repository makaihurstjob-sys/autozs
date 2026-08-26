const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(`${__dirname}/ebay-customer-message.js`, "utf8");

class FakeControl {
  constructor(tagName) {
    this.tagName = tagName;
    this.disabled = false;
    this.isContentEditable = false;
    this.events = [];
    this._value = "";
  }

  get value() {
    return this._value;
  }

  set value(value) {
    this._value = String(value);
  }

  getBoundingClientRect() {
    return { width: 300, height: 100 };
  }

  focus() {}

  dispatchEvent(event) {
    this.events.push(event.type);
  }
}

class FakeTextArea extends FakeControl {
  constructor() {
    super("TEXTAREA");
  }
}

class FakeInput extends FakeControl {
  constructor() {
    super("INPUT");
  }
}

async function runComposerFillTest() {
  const composer = new FakeTextArea();
  const subject = new FakeInput();
  const statusUpdates = [];
  let notice = null;

  const document = {
    body: {
      innerText: "",
      appendChild(element) {
        notice = element;
      },
    },
    documentElement: { appendChild() {} },
    getElementById(id) {
      return id === "autozs-customer-message-notice" ? notice : null;
    },
    createElement() {
      const label = { textContent: "" };
      return {
        id: "",
        style: {},
        set innerHTML(_value) {
          this.label = label;
        },
        querySelector(selector) {
          return selector === "span" ? label : null;
        },
      };
    },
    querySelectorAll(selector) {
      if (selector.includes("textarea")) return [composer];
      if (selector.includes('input[name*="subject"')) return [subject];
      return [];
    },
    addEventListener() {},
  };

  const context = {
    console,
    URLSearchParams,
    location: {
      search: "?autozs_customer_message=5",
      hash: "",
    },
    window: { addEventListener() {} },
    document,
    HTMLTextAreaElement: FakeTextArea,
    HTMLInputElement: FakeInput,
    InputEvent: class InputEvent {
      constructor(type) {
        this.type = type;
      }
    },
    Event: class Event {
      constructor(type) {
        this.type = type;
      }
    },
    setTimeout,
    clearTimeout,
    setInterval: () => 1,
    clearInterval: () => {},
    chrome: {
      runtime: {
        sendMessage: async (message) => {
          if (message.type === "autozs-customer-message-payload") {
            return {
              ok: true,
              payload: {
                message: {
                  id: 5,
                  subject: "Important order update",
                  body: "Bilingual customer refund reply",
                },
              },
            };
          }
          if (message.type === "autozs-customer-message-status") {
            statusUpdates.push(message.payload);
            return { ok: true };
          }
          throw new Error(`Unexpected message ${JSON.stringify(message)}`);
        },
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise((resolve) => setTimeout(resolve, 400));

  if (composer.value !== "Bilingual customer refund reply") {
    throw new Error(`Expected the queued reply in the eBay composer, got ${composer.value}`);
  }
  if (subject.value !== "Important order update") {
    throw new Error(`Expected the queued subject in the eBay composer, got ${subject.value}`);
  }
  if (!composer.events.includes("input") || !composer.events.includes("change")) {
    throw new Error(`Expected native input events, got ${JSON.stringify(composer.events)}`);
  }
  if (!statusUpdates.some((update) => String(update.error || "").includes("awaiting your review"))) {
    throw new Error(`Expected AutoZS to record manual review state, got ${JSON.stringify(statusUpdates)}`);
  }
  if (!notice?.label?.textContent.includes("press eBay")) {
    throw new Error(`Expected a manual Send instruction, got ${notice?.label?.textContent}`);
  }
}

// The Orders-list runner has to click through "More actions" -> "Message
// buyer" before any composer exists at all -- order-details deep links
// regularly fail to load ("Unfortunately there has been an error retrieving
// your order"), independent of which ID is passed, so this click-through is
// the one path that was verified live to resolve reliably.
async function runClickThroughDiscoveryTest() {
  const composer = new FakeTextArea();
  let stage = 0; // 0: nothing open, 1: actions menu open, 2: message panel open

  const moreActionsToggle = {
    tagName: "BUTTON",
    innerText: "",
    getBoundingClientRect: () => ({ width: 20, height: 20 }),
    getAttribute: (name) => (name === "aria-label" ? "Show more actions" : null),
    click: () => { stage = Math.max(stage, 1); },
  };
  // Carries hidden accessibility text past the visible label, same as the
  // real button ("Message buyer\nfor order number 22-15024-78151") -- the
  // discovery match has to be starts-with, not exact.
  const messageBuyerButton = {
    tagName: "BUTTON",
    innerText: "Message buyer\nfor order number 22-15024-78151",
    getBoundingClientRect: () => ({ width: 120, height: 20 }),
    getAttribute: () => null,
    click: () => { stage = Math.max(stage, 2); },
  };
  // The real menu item is this <li> wrapping the button above, carrying the
  // same visible text but no click handler of its own. It comes first in
  // document order, so clicking whatever a combined "button, li" query
  // returns first hits this instead of the real button.
  const messageBuyerListWrapper = {
    tagName: "LI",
    innerText: "Message buyer\nfor order number 22-15024-78151",
    getBoundingClientRect: () => ({ width: 120, height: 20 }),
    getAttribute: () => null,
    click: () => { throw new Error("Clicked the non-interactive <li> wrapper instead of the real button"); },
  };

  const document = {
    body: { innerText: "", appendChild() {} },
    documentElement: { appendChild() {} },
    getElementById: () => null,
    createElement() {
      const label = { textContent: "" };
      return { id: "", style: {}, set innerHTML(_v) { this.label = label; }, querySelector: (s) => (s === "span" ? label : null) };
    },
    querySelectorAll(selector) {
      if (selector.includes("textarea")) return stage >= 2 ? [composer] : [];
      if (selector === "iframe") return [];
      if (selector === "button") {
        if (stage === 0) return [moreActionsToggle];
        if (stage === 1) return [messageBuyerButton];
        return [];
      }
      if (selector.includes('[aria-label="Show more actions"]')) return stage === 0 ? [moreActionsToggle] : [];
      if (selector.includes("li,")) return stage === 1 ? [messageBuyerListWrapper] : [];
      return [];
    },
    addEventListener() {},
  };

  const context = {
    console,
    URLSearchParams,
    location: { search: "?autozs_customer_message=6", hash: "" },
    window: { addEventListener() {} },
    document,
    HTMLTextAreaElement: FakeTextArea,
    HTMLInputElement: FakeInput,
    InputEvent: class InputEvent { constructor(type) { this.type = type; } },
    Event: class Event { constructor(type) { this.type = type; } },
    setTimeout,
    clearTimeout,
    setInterval: () => 1,
    clearInterval: () => {},
    chrome: {
      runtime: {
        sendMessage: async (message) => {
          if (message.type === "autozs-customer-message-payload") {
            return { ok: true, payload: { message: { id: 6, subject: "", body: "Thanks for your order" } } };
          }
          if (message.type === "autozs-customer-message-status") return { ok: true };
          throw new Error(`Unexpected message ${JSON.stringify(message)}`);
        },
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  // Two 500ms discovery ticks (open the menu, then click the item) plus
  // margin for the initial 250ms settle delay.
  await new Promise((resolve) => setTimeout(resolve, 1400));

  if (stage !== 2) {
    throw new Error(`Expected the click-through to reach the message panel (stage 2), got stage ${stage}`);
  }
  if (composer.value !== "Thanks for your order") {
    throw new Error(`Expected the queued reply filled in once discovered, got ${composer.value}`);
  }
}

async function runCrossOriginFrameRelayTest() {
  const composer = new FakeTextArea();
  const statusUpdates = [];
  let messageListener = null;
  const frameWindow = {
    top: {},
    addEventListener(type, listener) {
      if (type === "message") messageListener = listener;
    },
  };
  frameWindow.self = frameWindow;
  const document = {
    body: { innerText: "", appendChild() {} },
    documentElement: { appendChild() {} },
    getElementById: () => null,
    createElement: () => ({ style: {}, querySelector: () => null }),
    querySelectorAll(selector) {
      if (selector.includes("textarea")) return [composer];
      return [];
    },
    addEventListener() {},
  };
  const context = {
    console,
    URLSearchParams,
    location: { search: "", hash: "" },
    window: frameWindow,
    document,
    HTMLTextAreaElement: FakeTextArea,
    HTMLInputElement: FakeInput,
    InputEvent: class InputEvent { constructor(type) { this.type = type; } },
    Event: class Event { constructor(type) { this.type = type; } },
    setTimeout,
    clearTimeout,
    setInterval: () => 1,
    clearInterval: () => {},
    chrome: {
      runtime: {
        sendMessage: async (message) => {
          if (message.type === "autozs-customer-message-payload") {
            if (message.messageId !== 7) throw new Error(`Expected relayed message ID 7, got ${message.messageId}`);
            return { ok: true, payload: { message: { id: 7, subject: "", body: "Reply filled inside the iframe" } } };
          }
          if (message.type === "autozs-customer-message-status") {
            statusUpdates.push(message.payload);
            return { ok: true };
          }
          throw new Error(`Unexpected message ${JSON.stringify(message)}`);
        },
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  if (!messageListener) throw new Error("Expected the child frame to listen for the parent message ID relay");
  messageListener({ data: { autozsCustomerMessageId: 7 } });
  await new Promise((resolve) => setTimeout(resolve, 400));

  if (composer.value !== "Reply filled inside the iframe") {
    throw new Error(`Expected the child frame to fill its own composer, got ${composer.value}`);
  }
  if (!statusUpdates.some((update) => update.status === "prepared")) {
    throw new Error(`Expected the iframe runner to report prepared, got ${JSON.stringify(statusUpdates)}`);
  }
}

runComposerFillTest()
  .then(runClickThroughDiscoveryTest)
  .then(runCrossOriginFrameRelayTest)
  .then(() => console.log("ebay customer message tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
