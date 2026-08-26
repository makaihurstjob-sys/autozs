(() => {
const BUILD_VERSION = "0.1.0";
const ALARM = "master-dashboard-browser-bridge";
const DEFAULT_URL = "http://127.0.0.1:8791";
const diagnosticSessions = new Map();
const localConfig = globalThis.MASTER_DASHBOARD_BROWSER_BRIDGE_CONFIG || {};

function safeText(value, max = 2_000) {
  return String(value ?? "").slice(0, max);
}

function safeEvent(method, params) {
  const value = JSON.stringify({ method, params });
  return value.length > 24_000
    ? { method, params: { truncated: true, preview: value.slice(0, 23_000) } }
    : JSON.parse(value);
}

async function settings() {
  const stored = await chrome.storage.local.get(["dashboardUrl", "bridgeToken", "agentId"]);
  let agentId = safeText(stored.agentId, 100);
  if (!agentId) {
    agentId = `windows-${crypto.randomUUID()}`;
    await chrome.storage.local.set({ agentId });
  }
  return {
    dashboardUrl: safeText(stored.dashboardUrl || localConfig.dashboardUrl || DEFAULT_URL, 500).replace(/\/+$/, ""),
    bridgeToken: safeText(stored.bridgeToken || localConfig.bridgeToken, 500),
    agentId,
  };
}

async function bridgeFetch(path, options = {}) {
  const config = await settings();
  if (config.bridgeToken.length < 32) throw new Error("Open the extension options and save the browser bridge token.");
  const response = await fetch(config.dashboardUrl + path, {
    ...options,
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      "x-browser-bridge-token": config.bridgeToken,
      ...(options.headers || {}),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Dashboard returned ${response.status}.`);
  return body;
}

async function tabInventory() {
  const tabs = await chrome.tabs.query({});
  return tabs.slice(0, 200).map((tab) => ({
    id: tab.id,
    windowId: tab.windowId,
    title: safeText(tab.title, 300),
    url: safeText(tab.url || tab.pendingUrl, 2_000),
    active: Boolean(tab.active),
    status: safeText(tab.status, 40),
    debuggable: !String(tab.url || "").startsWith("chrome://"),
  }));
}

async function heartbeat() {
  const config = await settings();
  return bridgeFetch("/api/browser-bridge/agent/heartbeat", {
    method: "POST",
    body: JSON.stringify({
      agentId: config.agentId,
      buildVersion: BUILD_VERSION,
      browserVersion: navigator.userAgent,
      extensionId: chrome.runtime.id,
      tabs: await tabInventory(),
    }),
  });
}

async function withDebugger(tabId, callback, keepAttached = false) {
  const target = { tabId };
  const alreadyAttached = diagnosticSessions.has(tabId);
  if (!alreadyAttached) await chrome.debugger.attach(target, "1.3");
  try {
    return await callback(target);
  } finally {
    if (!alreadyAttached && !keepAttached) await chrome.debugger.detach(target).catch(() => {});
  }
}

async function inspectTab(tabId) {
  const frames = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    func: () => ({
      extensionVersion: chrome.runtime?.getManifest?.().version || "",
      url: location.href,
      title: document.title,
      readyState: document.readyState,
      bodyText: String(document.body?.innerText || "").replace(/\s+/g, " ").slice(0, 8_000),
      iframes: [...document.querySelectorAll("iframe")].slice(0, 50).map((frame) => ({
        src: frame.src || "",
        title: frame.title || "",
        name: frame.name || "",
      })),
      controls: [...document.querySelectorAll("textarea,input,button,[contenteditable=true]")].slice(0, 200).map((element) => ({
        tag: element.tagName,
        type: element.getAttribute("type") || "",
        name: element.getAttribute("name") || "",
        id: element.id || "",
        ariaLabel: element.getAttribute("aria-label") || "",
        placeholder: element.getAttribute("placeholder") || "",
        text: String(element.innerText || element.value || "").replace(/\s+/g, " ").slice(0, 300),
      })),
    }),
  });
  return { frames: frames.map((entry) => ({ frameId: entry.frameId, document: entry.result })) };
}

async function openListingJob(tabId, payload = {}) {
  const jobId = Number(payload.jobId);
  if (!Number.isSafeInteger(jobId) || jobId <= 0) throw new Error("Choose a valid AUTOZS listing-job ID.");
  const response = await fetch(`http://127.0.0.1:8000/listing-jobs/${jobId}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`AUTOZS listing job ${jobId} returned ${response.status}.`);
  const job = await response.json();
  if (job.status !== "running") throw new Error(`AUTOZS listing job ${jobId} is not running.`);
  const target = new URL(String(job.assistant_url || ""));
  const targetJobId = target.searchParams.get("autozs_job_id") || new URLSearchParams(target.hash.replace(/^#/, "")).get("autozs_job_id");
  if (target.protocol !== "https:" || !["www.ebay.com", "sell.ebay.com"].includes(target.hostname) || targetJobId !== String(jobId)) {
    throw new Error("AUTOZS returned an invalid eBay listing-runner URL.");
  }
  const tab = await chrome.tabs.update(Number(tabId), { url: target.href, active: true });
  return { tabId: tab.id, jobId, url: target.href };
}

function homeDepotConfirmationNumber(payload = {}) {
  const orderNumber = String(payload.orderNumber || "").trim().toUpperCase();
  if (!/^WK\d{8}$/.test(orderNumber)) throw new Error("Choose a valid Home Depot confirmation number.");
  return orderNumber;
}

function homeDepotOrderUrl(orderNumber) {
  const target = new URL("https://www.homedepot.com/order/view/orderdetails");
  target.searchParams.set("orderId", orderNumber);
  return target;
}

async function readHomeDepotOrder(tabId, payload = {}) {
  const orderNumber = homeDepotConfirmationNumber(payload);
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: Number(tabId) },
    args: [orderNumber],
    func: (expectedOrderNumber) => {
      const url = new URL(location.href);
      const bodyText = String(document.body?.innerText || "").replace(/\s+/g, " ").trim();
      const pageOrderNumber = String(url.searchParams.get("orderId") || "").trim().toUpperCase();
      if (url.hostname !== "www.homedepot.com" || pageOrderNumber !== expectedOrderNumber || !bodyText.includes(expectedOrderNumber)) {
        return { matched: false, error: "The open page does not show the requested Home Depot order." };
      }
      if (/pardon our dust|internal homedepot\.com error|page you are looking for no longer exists/i.test(bodyText)) {
        return { matched: false, error: "Home Depot did not return a readable order page." };
      }
      const moneyAfter = (labels) => {
        for (const label of labels) {
          const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          const match = bodyText.match(new RegExp(`${escaped}\\s*:?\\s*\\$\\s*([0-9]{1,6}(?:,[0-9]{3})*(?:\\.\\d{2})?)`, "i"));
          if (match) return Number(match[1].replace(/,/g, ""));
        }
        return null;
      };
      const total = moneyAfter(["Order Total", "Total Charged", "Total"]);
      return {
        matched: true,
        orderNumber: expectedOrderNumber,
        orderUrl: url.href,
        itemSubtotal: moneyAfter(["Item Subtotal", "Subtotal"]),
        salesTax: moneyAfter(["Sales Tax", "Tax"]),
        shipping: moneyAfter(["Shipping", "Delivery"]),
        discounts: moneyAfter(["Discounts", "Discount", "Savings"]),
        total,
        capturedAt: new Date().toISOString(),
        complete: Number.isFinite(total) && total > 0,
      };
    },
  });
  if (!result?.matched) throw new Error(result?.error || "The Home Depot order could not be read.");
  return result;
}

async function screenshotTab(tabId) {
  return withDebugger(tabId, async (target) => {
    await chrome.debugger.sendCommand(target, "Page.enable");
    const shot = await chrome.debugger.sendCommand(target, "Page.captureScreenshot", { format: "jpeg", quality: 55, fromSurface: true });
    return { mimeType: "image/jpeg", data: safeText(shot.data, 2_700_000) };
  });
}

async function startDiagnostic(tabId) {
  if (diagnosticSessions.has(tabId)) return { started: false, alreadyRunning: true };
  const target = { tabId };
  await chrome.debugger.attach(target, "1.3");
  diagnosticSessions.set(tabId, { events: [], startedAt: new Date().toISOString() });
  await Promise.all([
    chrome.debugger.sendCommand(target, "Network.enable", { maxTotalBufferSize: 5_000_000, maxResourceBufferSize: 1_000_000 }),
    chrome.debugger.sendCommand(target, "Runtime.enable"),
    chrome.debugger.sendCommand(target, "Log.enable"),
    chrome.debugger.sendCommand(target, "Page.enable"),
  ]);
  return { started: true };
}

async function readDiagnostic(tabId) {
  const session = diagnosticSessions.get(tabId);
  if (!session) throw new Error("No diagnostic session is active for that tab.");
  const target = { tabId };
  const frameTree = await chrome.debugger.sendCommand(target, "Page.getFrameTree").catch(() => null);
  const events = session.events.splice(0, session.events.length);
  return { startedAt: session.startedAt, frameTree, events };
}

async function stopDiagnostic(tabId) {
  const session = diagnosticSessions.get(tabId);
  if (!session) return { stopped: false, alreadyStopped: true };
  diagnosticSessions.delete(tabId);
  await chrome.debugger.detach({ tabId }).catch(() => {});
  return { stopped: true, events: session.events };
}

chrome.debugger.onEvent.addListener((source, method, params) => {
  const session = diagnosticSessions.get(source.tabId);
  if (!session) return;
  if (!["Network.loadingFailed", "Network.responseReceived", "Runtime.consoleAPICalled", "Runtime.exceptionThrown", "Log.entryAdded", "Page.frameAttached", "Page.frameNavigated"].includes(method)) return;
  session.events.push({ at: new Date().toISOString(), ...safeEvent(method, params) });
  if (session.events.length > 1_000) session.events.splice(0, session.events.length - 1_000);
});

chrome.debugger.onDetach.addListener((source) => diagnosticSessions.delete(source.tabId));

async function executeCommand(command) {
  switch (command.type) {
    case "tabs.list": return { tabs: await tabInventory() };
    case "tab.inspect": return inspectTab(command.tabId);
    case "autozs.openListingJob": return openListingJob(command.tabId, command.payload);
    case "tab.screenshot": return screenshotTab(command.tabId);
    case "diagnostic.start": return startDiagnostic(command.tabId);
    case "diagnostic.read": return readDiagnostic(command.tabId);
    case "diagnostic.stop": return stopDiagnostic(command.tabId);
    case "autozs.customerMessagePoll": {
      const response = await chrome.runtime.sendMessage({ type: "autozs-customer-message-poll-now" });
      if (!response?.ok) throw new Error(response?.error || "AUTOZS customer-message poll failed.");
      return response;
    }
    case "autozs.openOrder": {
      const orderId = String(command.payload?.orderId || "").trim();
      if (!/^\d{2}-\d{5}-\d{5}$/.test(orderId)) throw new Error("Choose a valid eBay order number.");
      const target = new URL("https://www.ebay.com/sh/ord");
      target.searchParams.set("q", orderId);
      const tab = await chrome.tabs.create({ url: target.href, active: true });
      return { tabId: tab.id, url: target.href };
    }
    case "autozs.openHomeDepotOrder": {
      const orderNumber = homeDepotConfirmationNumber(command.payload);
      const target = homeDepotOrderUrl(orderNumber);
      const tab = await chrome.tabs.create({ url: target.href, active: false });
      return { tabId: tab.id, orderNumber, url: target.href };
    }
    case "autozs.readHomeDepotOrder": return readHomeDepotOrder(command.tabId, command.payload);
    case "autozs.openAddTracking": {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: Number(command.tabId) },
        func: () => {
          const visible = (element) => {
            const rect = element?.getBoundingClientRect?.();
            return Boolean(rect && rect.width > 0 && rect.height > 0 && !element.disabled);
          };
          const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
          const buttons = [...document.querySelectorAll("button, [role='button']")];
          const button = buttons.find((element) => visible(element) && normalize(element.textContent || element.innerText) === "add tracking")
            || buttons.find((element) => visible(element) && normalize(element.textContent || element.innerText).startsWith("add tracking number"))
            || buttons.find((element) => visible(element) && normalize(element.textContent || element.innerText).includes("add tracking"));
          if (!button) return { opened: false, error: "Add tracking was not found on this eBay order." };
          button.click();
          return { opened: true };
        },
      });
      if (!result?.opened) throw new Error(result?.error || "Could not open eBay tracking.");
      return result;
    }
    case "autozs.fillTracking": {
      const trackingNumber = String(command.payload?.trackingNumber || "").trim();
      const carrier = String(command.payload?.carrier || "").trim();
      if (!/^[A-Za-z0-9-]{8,40}$/.test(trackingNumber)) throw new Error("Choose a valid tracking number.");
      if (!carrier || carrier.length > 40) throw new Error("Choose a valid carrier.");
      const frames = await chrome.scripting.executeScript({
        target: { tabId: Number(command.tabId), allFrames: true },
        args: [trackingNumber, carrier],
        func: async (number, carrierName) => {
          if (!location.pathname.includes("/ship/trk/trackings")) return { matched: false };
          const inputs = [...document.querySelectorAll('input[type="text"]')].filter((element) => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && !element.disabled;
          });
          if (inputs.length < 2) return { matched: true, filled: false, error: "Tracking fields were not found." };
          const setValue = (element, value) => {
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
            if (setter) setter.call(element, value); else element.value = value;
            element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
            element.dispatchEvent(new Event("change", { bubbles: true }));
          };
          setValue(inputs[0], number);
          setValue(inputs[1], carrierName);
          inputs[1].focus();
          await new Promise((resolve) => setTimeout(resolve, 600));
          const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
          const option = [...document.querySelectorAll('[role="option"], li, button, div')].find((element) => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && normalize(element.textContent || element.innerText) === normalize(carrierName);
          });
          if (option) {
            option.click();
            await new Promise((resolve) => setTimeout(resolve, 400));
          }
          for (const key of ["ArrowDown", "Enter"]) {
            inputs[1].dispatchEvent(new KeyboardEvent("keydown", { key, code: key, bubbles: true }));
            inputs[1].dispatchEvent(new KeyboardEvent("keyup", { key, code: key, bubbles: true }));
            await new Promise((resolve) => setTimeout(resolve, 150));
          }
          inputs[1].blur();
          inputs[0].blur();
          await new Promise((resolve) => setTimeout(resolve, 800));
          const save = [...document.querySelectorAll("button")].find((element) => normalize(element.textContent || element.innerText) === "save and continue");
          return {
            matched: true,
            filled: true,
            trackingNumber: inputs[0].value,
            carrier: carrierName,
            carrierSelected: Boolean(option),
            saveEnabled: Boolean(save && !save.disabled && save.getAttribute("aria-disabled") !== "true"),
          };
        },
      });
      const result = frames.map((entry) => entry.result).find((entry) => entry?.matched);
      if (!result?.filled) throw new Error(result?.error || "eBay tracking form was not open.");
      return result;
    }
    case "autozs.submitTracking": {
      const frames = await chrome.scripting.executeScript({
        target: { tabId: Number(command.tabId), allFrames: true },
        func: () => {
          if (!location.pathname.includes("/ship/trk/trackings")) return { matched: false };
          const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
          const button = [...document.querySelectorAll("button")].find((element) => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && !element.disabled
              && normalize(element.textContent || element.innerText) === "save and continue";
          });
          if (!button) return { matched: true, submitted: false, error: "Save and continue was not available." };
          button.click();
          return { matched: true, submitted: true };
        },
      });
      const result = frames.map((entry) => entry.result).find((entry) => entry?.matched);
      if (!result?.submitted) throw new Error(result?.error || "eBay tracking form was not open.");
      return result;
    }
    default: throw new Error("Unsupported browser bridge command.");
  }
}

async function pollOnce() {
  await heartbeat();
  const config = await settings();
  const body = await bridgeFetch(`/api/browser-bridge/agent/commands/next?agentId=${encodeURIComponent(config.agentId)}`);
  if (!body.command) return;
  try {
    const result = await executeCommand(body.command);
    const config = await settings();
    await bridgeFetch(`/api/browser-bridge/agent/commands/${body.command.id}/result`, {
      method: "POST",
      body: JSON.stringify({ agentId: config.agentId, ok: true, result }),
    });
  } catch (error) {
    const config = await settings();
    await bridgeFetch(`/api/browser-bridge/agent/commands/${body.command.id}/result`, {
      method: "POST",
      body: JSON.stringify({ agentId: config.agentId, ok: false, error: safeText(error?.message || error, 2_000) }),
    }).catch(() => {});
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.runtime.openOptionsPage();
  chrome.alarms.create(ALARM, { delayInMinutes: 0.05, periodInMinutes: 0.1 });
});
chrome.runtime.onStartup.addListener(() => chrome.alarms.create(ALARM, { delayInMinutes: 0.05, periodInMinutes: 0.1 }));
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === ALARM) pollOnce().catch(() => {}); });
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "browser-bridge-test") return undefined;
  pollOnce().then(() => sendResponse({ ok: true })).catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
chrome.alarms.create(ALARM, { delayInMinutes: 0.05, periodInMinutes: 0.1 });
pollOnce().catch(() => {});
})();
