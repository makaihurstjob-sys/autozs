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
    window: {},
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

runComposerFillTest()
  .then(() => console.log("ebay customer message tests ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
