(function () {
  if (window !== window.top) return;

  const SESSION_KEY = "autozs_ebay_tracking_upload";

  function trackingRunnerIdentity(urlValue) {
    let url;
    try { url = new URL(String(urlValue || "")); } catch { return null; }
    const supplierOrderId = Number(url.searchParams.get("autozs_supplier_order_id") || 0);
    const ebayOrderId = String(url.searchParams.get("q") || "").trim();
    if (url.hostname !== "www.ebay.com" || url.pathname !== "/sh/ord"
      || url.searchParams.get("autozs_workflow") !== "tracking_upload"
      || !/^\d{2}-\d{5}-\d{5}$/.test(ebayOrderId)
      || !Number.isInteger(supplierOrderId) || supplierOrderId <= 0) return null;
    return { supplierOrderId, ebayOrderId };
  }

  function trackingPayloadIsSafe(candidate, identity) {
    return Boolean(candidate && identity
      && Number(candidate.supplier_order_id) === identity.supplierOrderId
      && candidate.ebay_order_id === identity.ebayOrderId
      && /^(UPS|FedEx|USPS|ONTRAC|LASERSHIP|LSO)$/i.test(String(candidate.carrier || ""))
      && /^[A-Z0-9]{8,40}$/i.test(String(candidate.tracking_number || "").replace(/[^A-Z0-9]/gi, "")));
  }

  function trackingSubmissionConfirmed(bodyText, candidate) {
    const text = String(bodyText || "").replace(/\s+/g, " ");
    const trackingNumber = String(candidate?.tracking_number || "").replace(/[^A-Z0-9]/gi, "").toUpperCase();
    const compactText = text.replace(/[^A-Z0-9]/gi, "").toUpperCase();
    return Boolean(candidate?.ebay_order_id
      && text.includes(candidate.ebay_order_id)
      && trackingNumber.length >= 8
      && compactText.includes(trackingNumber)
      && /tracking (?:was )?(?:successfully )?(?:added|saved)|marked as shipped|shipment updated/i.test(text));
  }

  function visible(element) {
    const rect = element?.getBoundingClientRect?.();
    return Boolean(rect && rect.width > 0 && rect.height > 0 && !element.disabled);
  }

  function normalize(value) {
    return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function setNativeValue(input, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (setter) setter.call(input, value); else input.value = value;
    input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function statusBanner(message, state = "working") {
    let host = document.getElementById("autozs-ebay-tracking-status");
    if (!host) {
      host = document.createElement("div");
      host.id = "autozs-ebay-tracking-status";
      host.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:2147483647;max-width:420px;padding:14px 16px;border-radius:10px;background:#10231c;color:#f4fbf8;border:1px solid #315b4a;font:13px/1.4 Arial,sans-serif;box-shadow:0 10px 35px rgba(0,0,0,.35);pointer-events:none";
      document.documentElement.append(host);
    }
    host.style.borderColor = state === "error" ? "#b84c58" : state === "ready" ? "#4dbb8b" : "#315b4a";
    host.textContent = message;
  }

  async function brokerCandidate(identity) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        type: "autozs-ebay-tracking-candidate",
        supplierOrderId: identity.supplierOrderId,
      }, (response) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else if (!response?.ok) reject(new Error(response?.error || "Tracking handoff was rejected."));
        else resolve(response.candidate);
      });
    });
  }

  async function openTrackingForm(candidate) {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const body = String(document.body?.innerText || "");
      if (!body.includes(candidate.ebay_order_id)) throw new Error("The visible eBay order does not match the tracking handoff.");
      const button = [...document.querySelectorAll("button,[role='button']")].find((element) => {
        const text = normalize(element.textContent || element.innerText);
        return visible(element) && (text === "add tracking" || text.startsWith("add tracking number") || text.includes("add tracking"));
      });
      if (button) {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(candidate));
        button.click();
        statusBanner("Exact eBay order verified. Opening Add Tracking…");
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new Error("Add Tracking was not found on the exact eBay order.");
  }

  async function fillTrackingForm(candidate) {
    if (!location.pathname.includes("/ship/trk/trackings")) return false;
    const inputs = [...document.querySelectorAll('input[type="text"]')].filter(visible);
    if (inputs.length < 2) throw new Error("eBay tracking fields were not found.");
    const trackingNumber = String(candidate.tracking_number).replace(/[^A-Z0-9]/gi, "").toUpperCase();
    const carrier = String(candidate.carrier).trim();
    setNativeValue(inputs[0], trackingNumber);
    setNativeValue(inputs[1], carrier);
    inputs[1].focus();
    await new Promise((resolve) => setTimeout(resolve, 600));
    const option = [...document.querySelectorAll('[role="option"],li,button,div')]
      .find((element) => visible(element) && normalize(element.textContent || element.innerText) === normalize(carrier));
    if (option) option.click();
    await new Promise((resolve) => setTimeout(resolve, 500));
    inputs[0].blur();
    inputs[1].blur();
    await new Promise((resolve) => setTimeout(resolve, 700));
    const save = [...document.querySelectorAll("button")]
      .find((element) => normalize(element.textContent || element.innerText) === "save and continue");
    if (inputs[0].value.replace(/[^A-Z0-9]/gi, "").toUpperCase() !== trackingNumber
      || normalize(inputs[1].value) !== normalize(carrier)
      || !save || save.disabled || save.getAttribute("aria-disabled") === "true") {
      throw new Error("eBay did not retain the exact tracking details with Save and Continue enabled.");
    }
    await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        type: "autozs-ebay-tracking-prepared",
        supplierOrderId: Number(candidate.supplier_order_id),
        trackingNumber,
      }, (response) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else if (!response?.ok) reject(new Error(response?.error || "Prepared tracking state was rejected."));
        else resolve();
      });
    });
    statusBanner("Tracking verified and ready. AUTOZS did not press Save and Continue.", "ready");
    watchForSubmission(candidate);
    return true;
  }

  async function reportSubmission(candidate) {
    const trackingNumber = String(candidate.tracking_number || "").replace(/[^A-Z0-9]/gi, "").toUpperCase();
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        type: "autozs-ebay-tracking-submitted",
        supplierOrderId: Number(candidate.supplier_order_id),
        trackingNumber,
      }, (response) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else if (!response?.ok) reject(new Error(response?.error || "Tracking confirmation was rejected."));
        else resolve();
      });
    });
  }

  function watchForSubmission(candidate) {
    let completed = false;
    const check = async () => {
      if (completed || !trackingSubmissionConfirmed(document.body?.innerText || "", candidate)) return;
      completed = true;
      observer.disconnect();
      await reportSubmission(candidate);
      sessionStorage.removeItem(SESSION_KEY);
      statusBanner("eBay confirmed tracking. AUTOZS queued an authoritative order re-sync.", "ready");
    };
    const observer = new MutationObserver(() => { check().catch((error) => statusBanner(`Tracking confirmation stopped: ${error.message}`, "error")); });
    observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
    setTimeout(() => observer.disconnect(), 30 * 60 * 1000);
    check().catch(() => {});
  }

  async function start() {
    const identity = trackingRunnerIdentity(location.href);
    if (identity) {
      const candidate = await brokerCandidate(identity);
      if (!trackingPayloadIsSafe(candidate, identity)) throw new Error("Tracking handoff identity or payload did not match.");
      await openTrackingForm(candidate);
      return;
    }
    let candidate = null;
    try { candidate = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); } catch {}
    if (candidate && location.pathname.includes("/ship/trk/trackings")) await fillTrackingForm(candidate);
    else if (candidate && trackingSubmissionConfirmed(document.body?.innerText || "", candidate)) {
      await reportSubmission(candidate);
      sessionStorage.removeItem(SESSION_KEY);
      statusBanner("eBay confirmed tracking. AUTOZS queued an authoritative order re-sync.", "ready");
    }
  }

  const run = () => start().catch((error) => statusBanner(`Tracking preparation stopped: ${error.message || String(error)}`, "error"));
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run, { once: true });
  else run();

  globalThis.autozsEbayTrackingUploadTest = { trackingRunnerIdentity, trackingPayloadIsSafe, trackingSubmissionConfirmed };
})();
