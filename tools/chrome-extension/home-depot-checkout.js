var AUTOZS_CHECKOUT_API = "https://desktop-56u49jf.tailb2892a.ts.net:8443";
var AUTOZS_CHECKOUT_BUILD = "2026-08-25-tracking-injection";
var AUTOZS_CHECKOUT_CART_REBUILD_KEY = "autozs-checkout-cart-rebuilt";
var AUTOZS_CHECKOUT_SESSION_KEY = "autozs_supplier_checkout";

function autozsCheckoutMoney(value) {
  const match = String(value || "").match(/\$\s*([0-9]{1,5}(?:,[0-9]{3})*(?:\.[0-9]{2})?)/);
  return match ? Number(match[1].replace(/,/g, "")) : null;
}

function autozsExpectedSupplierSubtotal(supplierOrder) {
  return Math.round(
    (supplierOrder?.items || []).reduce(
      (total, item) => total + Number(item?.unit_price || 0) * Math.max(1, Number(item?.quantity || 1)),
      0
    ) * 100
  ) / 100;
}

function autozsCheckoutPriceMismatch(expected, observed) {
  const tolerance = Math.max(0.05, Number(expected || 0) * 0.02);
  return !Number.isFinite(observed) || observed <= 0 || Math.abs(observed - Number(expected || 0)) > tolerance;
}

function autozsHomeDepotConfirmation(urlValue, bodyText = "") {
  let url;
  try { url = new URL(String(urlValue || "")); } catch { return null; }
  if (!/^\/order-confirmation\/?$/i.test(url.pathname)) return null;
  const externalOrderId = String(url.searchParams.get("orderId") || "").trim();
  if (!/^[A-Z0-9-]{6,128}$/i.test(externalOrderId)) return null;
  return { externalOrderId, bodyText: String(bodyText || "") };
}

function autozsConfirmationTotal(bodyText, approvedTotal) {
  const approved = Number(approvedTotal || 0);
  if (!Number.isFinite(approved) || approved <= 0) return null;
  const totals = autozsCheckoutTotals(bodyText);
  if (Number.isFinite(totals.total) && Math.abs(totals.total - approved) <= 0.01) return totals.total;
  const observed = [...String(bodyText || "").matchAll(/\$\s*([0-9]{1,5}(?:,[0-9]{3})*(?:\.\d{2}))/g)]
    .map((match) => Number(match[1].replace(/,/g, "")));
  return observed.some((value) => Math.abs(value - approved) <= 0.01) ? approved : null;
}

function autozsHomeDepotTrackingObservation(urlValue, bodyText = "") {
  let url;
  try { url = new URL(String(urlValue || "")); } catch { return null; }
  if (url.hostname !== "www.homedepot.com" || !/\/order\//i.test(url.pathname)) return null;
  const externalOrderId = String(url.searchParams.get("orderId") || "").trim();
  const text = String(bodyText || "").replace(/\s+/g, " ");
  if (!/^[A-Z0-9-]{6,128}$/i.test(externalOrderId) || !text.includes(externalOrderId)) return null;
  if (/pardon our dust|internal homedepot\.com error|page you are looking for no longer exists/i.test(text)) return null;
  const carrierMatch = text.match(/\b(UPS|FedEx|USPS|OnTrac|LaserShip|LSO)\b/i);
  const trackingMatch = text.match(/tracking\s*(?:number|no\.?|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9 -]{7,38}[A-Z0-9])/i);
  if (!carrierMatch || !trackingMatch) return null;
  const trackingNumber = trackingMatch[1].replace(/[\s-]+/g, "").toUpperCase();
  if (!/^[A-Z0-9]{8,40}$/.test(trackingNumber)) return null;
  const carrier = carrierMatch[1].toUpperCase() === "FEDEX" ? "FedEx" : carrierMatch[1].toUpperCase();
  const status = /\bdelivered\b/i.test(text)
    ? "delivered"
    : /\b(?:shipped|in transit|on (?:its|the) way)\b/i.test(text) ? "shipped" : null;
  return status ? { externalOrderId, carrier, trackingNumber, status } : null;
}

function autozsHomeDepotTrackingBlocked(urlValue, bodyText = "") {
  let url;
  try { url = new URL(String(urlValue || "")); } catch { return false; }
  return url.hostname === "www.homedepot.com"
    && url.searchParams.get("autozs_tracking_poll") === "1"
    && /^[A-Z0-9-]{6,128}$/i.test(url.searchParams.get("orderId") || "")
    && /pardon our dust|internal homedepot\.com error|page you are looking for no longer exists/i.test(String(bodyText || ""));
}

async function autozsObserveHomeDepotTracking() {
  const bodyText = document.body?.innerText || "";
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return false;
  if (autozsHomeDepotTrackingBlocked(location.href, bodyText)) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "autozs-supplier-tracking-blocked" }, (response) => {
        resolve(Boolean(!chrome.runtime.lastError && response?.ok));
      });
    });
  }
  const observation = autozsHomeDepotTrackingObservation(location.href, bodyText);
  if (!observation) return false;
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: "autozs-supplier-tracking-observation", ...observation }, (response) => {
      resolve(Boolean(!chrome.runtime.lastError && response?.ok));
    });
  });
}

async function autozsObserveHomeDepotTrackingBounded() {
  const params = new URLSearchParams(location.search);
  const markedPoll = params.get("autozs_tracking_poll") === "1";
  const attempts = markedPoll ? 20 : 1;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (await autozsObserveHomeDepotTracking().catch(() => false)) return true;
    if (attempt + 1 < attempts) await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return false;
}

function autozsCheckoutAddressText(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim()
    .toLowerCase();
}

function autozsChooseCheckoutCity(options, expectedCity, expectedState) {
  const city = autozsCheckoutAddressText(expectedCity);
  const state = autozsCheckoutAddressText(expectedState);
  if (!city || !state) return null;
  const matches = (options || []).filter((option) => {
    const optionCity = autozsCheckoutAddressText(option?.city || option?.label || option?.text || option?.value);
    const optionState = autozsCheckoutAddressText(option?.state || option?.label || option?.text || option?.value);
    return optionCity.includes(city) && optionState.includes(state);
  });
  return matches.length === 1 ? matches[0] : null;
}

function autozsCheckoutAddressMatches(expected, observed) {
  const equal = (field) => autozsCheckoutAddressText(expected?.[field]) === autozsCheckoutAddressText(observed?.[field]);
  const expectedPostal = String(expected?.postal_code || "").replace(/\D/g, "");
  const observedPostal = String(observed?.postal_code || "").replace(/\D/g, "");
  return equal("recipient_name")
    && equal("address_line1")
    && equal("address_line2")
    && equal("city")
    && equal("state")
    && expectedPostal.length >= 5
    && expectedPostal.slice(0, 5) === observedPostal.slice(0, 5);
}

function autozsCheckoutStaticCityState(text) {
  const match = String(text || "").match(/\bcity, state\b\s*([^\n,]+),\s*([A-Z]{2})\b/i);
  return match ? { city: match[1].trim(), state: match[2].toUpperCase() } : null;
}

function autozsCheckoutDeliveryState(text, visible, disabled) {
  const deliveryText = String(text || "");
  return {
    visible: Boolean(visible),
    enabled: Boolean(visible && !disabled),
    free: /Delivery Options[\s\S]{0,900}\bFREE\b/i.test(deliveryText),
    unavailable: /delivery cost can.t be calculated|delivery is no longer available/i.test(deliveryText),
  };
}

function autozsCheckoutOverlay() {
  let host = document.getElementById("autozs-supplier-checkout-overlay");
  if (host) return host;
  host = document.createElement("div");
  host.id = "autozs-supplier-checkout-overlay";
  host.style.cssText = [
    "position:fixed", "inset:0", "z-index:2147483647", "background:rgba(6,14,11,.80)",
    "display:flex", "align-items:center", "justify-content:center", "font-family:Arial,sans-serif", "pointer-events:none",
  ].join(";");
  host.innerHTML = `
    <div style="width:min(440px,calc(100vw - 32px));background:#0c1c16;color:#f3faf7;border:1px solid #28463a;border-radius:12px;padding:24px;box-shadow:0 18px 55px rgba(0,0,0,.5)">
      <div style="font-size:12px;color:#63d9b2;font-weight:700;letter-spacing:.08em;text-transform:uppercase">Home Depot checkout canary</div>
      <h2 style="font-size:24px;margin:10px 0 8px">AutoZS is verifying this order</h2>
      <p data-autozs-checkout-message style="font-size:14px;line-height:1.5;color:#b8c8c1;margin:0 0 16px">Loading the approved supplier order…</p>
      <div style="height:8px;background:#1d332a;border-radius:999px;overflow:hidden"><div data-autozs-checkout-bar style="height:100%;width:10%;background:#50c9a7;transition:width .25s"></div></div>
      <div data-autozs-checkout-percent style="text-align:center;font-size:12px;font-weight:700;margin-top:10px">10%</div>
      <div style="font-size:11px;color:#82958d;margin-top:14px">AutoZS will not submit payment from this canary.</div>
    </div>`;
  document.documentElement.append(host);
  return host;
}

function autozsCheckoutProgress(percent, message, state = "working") {
  const host = autozsCheckoutOverlay();
  const safePercent = Math.max(0, Math.min(100, Number(percent || 0)));
  host.querySelector("[data-autozs-checkout-message]").textContent = message;
  host.querySelector("[data-autozs-checkout-percent]").textContent = `${Math.round(safePercent)}%`;
  const bar = host.querySelector("[data-autozs-checkout-bar]");
  bar.style.width = `${safePercent}%`;
  bar.style.background = state === "error" ? "#ff6b78" : state === "complete" ? "#50c982" : "#50c9a7";
}

async function autozsCheckoutApi(path, options = {}) {
  if (typeof chrome !== "undefined" && chrome.runtime?.sendMessage && /^\/supplier-orders\/\d+$/.test(path)) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        type: "autozs-supplier-checkout-api",
        path,
        method: options.method || "GET",
        body: options.body || "",
      }, (response) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else if (!response?.ok) reject(new Error(response?.error || "Checkout API broker failed."));
        else resolve(response.data);
      });
    });
  }
  const response = await fetch(`${AUTOZS_CHECKOUT_API}${path}`, {
    cache: "no-store",
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.detail || `AutoZS API returned ${response.status}`);
  }
  return response.json();
}

async function autozsMarkCheckoutReview(supplierOrderId, reason, totals = {}) {
  return autozsCheckoutApi(`/supplier-orders/${Number(supplierOrderId)}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: "needs_review",
      failure_reason: reason,
      ...totals,
    }),
  });
}

async function autozsReconcileHomeDepotConfirmation(supplierOrderId, supplierOrder) {
  const confirmation = autozsHomeDepotConfirmation(location.href, document.body?.innerText || "");
  if (!confirmation) return false;
  if (supplierOrder.status === "placed" && supplierOrder.external_order_id === confirmation.externalOrderId) {
    autozsCheckoutProgress(100, `Home Depot order ${confirmation.externalOrderId} is recorded in AUTOZS.`, "complete");
    return true;
  }
  if (!["placing", "needs_review"].includes(supplierOrder.status)) {
    throw new Error(`Home Depot confirmed an order, but supplier order #${supplierOrderId} is ${supplierOrder.status}.`);
  }
  if (supplierOrder.external_order_id && supplierOrder.external_order_id !== confirmation.externalOrderId) {
    throw new Error(`Home Depot confirmation ${confirmation.externalOrderId} conflicts with the recorded supplier confirmation.`);
  }
  const confirmedTotal = autozsConfirmationTotal(confirmation.bodyText, supplierOrder.approved_total);
  if (confirmedTotal === null) {
    throw new Error(`Home Depot confirmation ${confirmation.externalOrderId} did not show the approved $${Number(supplierOrder.approved_total || 0).toFixed(2)} total.`);
  }
  await autozsCheckoutApi(`/supplier-orders/${Number(supplierOrderId)}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: "placed",
      external_order_id: confirmation.externalOrderId,
      total: confirmedTotal,
      failure_reason: "",
    }),
  });
  autozsCheckoutProgress(100, `Home Depot order ${confirmation.externalOrderId} was confirmed and recorded in AUTOZS.`, "complete");
  return true;
}

function autozsSetNativeInputValue(input, value) {
  const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value");
  descriptor?.set?.call(input, String(value));
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function autozsCheckoutField(selectors) {
  for (const selector of selectors) {
    const field = document.querySelector(selector);
    if (field && !field.disabled) return field;
  }
  return null;
}

function autozsFillCheckoutField(selectors, value, label, required = true) {
  const field = autozsCheckoutField(selectors);
  if (!field) {
    if (required) throw new Error(`Home Depot's ${label} field was not found.`);
    return null;
  }
  autozsSetNativeInputValue(field, value || "");
  field.dispatchEvent(new Event("blur", { bubbles: true }));
  return field;
}

function autozsCheckoutObservedAddress(fields) {
  const value = (field) => String(field?.value || field?.selectedOptions?.[0]?.textContent || "").trim();
  return {
    recipient_name: `${value(fields.firstName)} ${value(fields.lastName)}`.trim(),
    address_line1: value(fields.address1),
    address_line2: value(fields.address2),
    city: value(fields.city),
    state: value(fields.state),
    postal_code: value(fields.postal),
  };
}

function autozsSplitCheckoutName(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  return { firstName: parts.shift() || "", lastName: parts.join(" ") || "" };
}

function autozsCheckoutTotals(text) {
  const read = (label) => {
    const match = String(text || "").match(new RegExp(`\\b${label}\\b[\\s\\S]{0,80}?(\\$\\s*[0-9,]+(?:\\.[0-9]{2})?)`, "i"));
    return autozsCheckoutMoney(match?.[1]);
  };
  const body = String(text || "");
  const deliveryIsFree = /\bdelivery\b[\s\S]{0,40}?\bfree\b/i.test(body);
  const shipping = read("shipping") ?? (deliveryIsFree ? 0 : read("delivery"));
  return {
    subtotal: read("subtotal"),
    shipping,
    tax: read("(?:estimated\\s+sales\\s+tax|sales\\s+tax|tax)"),
    total: read("order total") ?? read("total"),
  };
}

function autozsCartPayableSubtotal(text) {
  const topTotal = String(text || "").match(/\btotal:\s*(\$\s*[0-9,]+(?:\.[0-9]{2})?)/i);
  if (topTotal) return autozsCheckoutMoney(topTotal[1]);
  const summaryTotal = String(text || "").match(/\byour order\b[\s\S]{0,500}?\btotal\b\s*(\$\s*[0-9,]+(?:\.[0-9]{2})?)/i);
  return autozsCheckoutMoney(summaryTotal?.[1]);
}

function autozsCheckoutTotalsAreSafe(totals, expectedSubtotal, approvedTotal) {
  if (autozsCheckoutPriceMismatch(expectedSubtotal, totals?.subtotal)) return false;
  if (![totals?.shipping, totals?.tax, totals?.total].every((value) => Number.isFinite(value) && value >= 0)) return false;
  const recomposed = Math.round((totals.subtotal + totals.shipping + totals.tax) * 100) / 100;
  return Math.abs(recomposed - totals.total) <= 0.02
    && Math.round(totals.total * 100) <= Math.round(Number(approvedTotal || 0) * 100);
}

async function autozsCheckoutCredential(supplierOrderId) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      { type: "autozs-supplier-checkout-credential", supplierOrderId: Number(supplierOrderId) },
      (response) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else if (!response?.ok) reject(new Error(response?.error || "Checkout credential was unavailable."));
        else resolve(response.credential);
      }
    );
  });
}

function autozsFindButton(pattern) {
  return [...document.querySelectorAll("button")].find((button) =>
    !button.disabled && pattern.test(String(button.innerText || button.textContent || "").trim())
  );
}

async function autozsNativeCheckoutClick(supplierOrderId, action) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({
      type: "autozs-supplier-native-click",
      supplierOrderId: Number(supplierOrderId),
      action,
    }, (response) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else if (!response?.ok) reject(new Error(response?.error || `Home Depot ${action} click failed.`));
      else resolve(response);
    });
  });
}

async function autozsNativeCheckoutFill(supplierOrderId, field, value) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({
      type: "autozs-supplier-native-fill",
      supplierOrderId: Number(supplierOrderId),
      field,
      value: String(value || ""),
    }, (response) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else if (!response?.ok) reject(new Error(response?.error || `Home Depot ${field} entry failed.`));
      else resolve(response);
    });
  });
}

async function autozsWaitForCheckoutButton(pattern, attempts = 20, delayMs = 500) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const button = autozsFindButton(pattern);
    if (button) return button;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return null;
}

async function autozsRunProductCheckoutCanary(supplierOrderId, supplierOrder) {
  autozsCheckoutProgress(28, "Reading the actual purchasable Home Depot price…");
  let captured = null;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    if (typeof captureSourceProductFromPage === "function") {
      try {
        captured = captureSourceProductFromPage();
      } catch {}
    }
    if (Number(captured?.source_price || 0) > 0) break;
    await new Promise((resolve) => setTimeout(resolve, 600));
  }
  const expectedSubtotal = autozsExpectedSupplierSubtotal(supplierOrder);
  const observedUnitPrice = Number(captured?.source_price || 0);
  const requestedQuantity = Math.max(1, Number(supplierOrder.items?.[0]?.quantity || 1));
  const observedSubtotal = Math.round(observedUnitPrice * requestedQuantity * 100) / 100;

  if (autozsCheckoutPriceMismatch(expectedSubtotal, observedSubtotal)) {
    const reason = `Checkout blocked: Home Depot's purchasable subtotal is $${observedSubtotal.toFixed(2)}, but AutoZS approved $${expectedSubtotal.toFixed(2)}. The displayed unit-rate price cannot be used as the order total.`;
    await autozsMarkCheckoutReview(supplierOrderId, reason, { item_subtotal: observedSubtotal, total: observedSubtotal });
    autozsCheckoutProgress(100, reason, "error");
    return;
  }

  autozsCheckoutProgress(52, `Price verified at $${observedSubtotal.toFixed(2)}. Selecting delivery and quantity ${requestedQuantity}…`);
  // Home Depot renders the price before its fulfillment controls. Wait for
  // the delivery widget instead of treating that normal render gap as an
  // unavailable item.
  const deliveryButton = await autozsWaitForCheckoutButton(/^delivery\b/i, 20, 500);
  if (deliveryButton) await autozsNativeCheckoutClick(supplierOrderId, "delivery");
  const quantityInput = document.querySelector(
    'input[name*="quantity" i], input[aria-label*="quantity" i], input[data-testid*="quantity" i]'
  );
  if (quantityInput) autozsSetNativeInputValue(quantityInput, requestedQuantity);
  const addToCart = await autozsWaitForCheckoutButton(/^add to cart$/i, 20, 500);
  if (!addToCart) {
    const reason = "Checkout paused: AutoZS verified the price but could not find Home Depot's Add to Cart button.";
    await autozsMarkCheckoutReview(supplierOrderId, reason);
    autozsCheckoutProgress(100, reason, "error");
    return;
  }
  autozsCheckoutProgress(68, "Adding the verified item to the cart…");
  sessionStorage.setItem(AUTOZS_CHECKOUT_SESSION_KEY, String(supplierOrderId));
  await autozsNativeCheckoutClick(supplierOrderId, "add_to_cart");
  await new Promise((resolve) => setTimeout(resolve, 2500));
  const cartUrl = new URL("https://www.homedepot.com/mycart/home");
  cartUrl.searchParams.set("autozs_supplier_order", String(supplierOrderId));
  cartUrl.searchParams.set("autozs_checkout_canary", "1");
  location.assign(cartUrl.href);
}

async function autozsRunCartCheckoutCanary(supplierOrderId, supplierOrder) {
  autozsCheckoutProgress(76, "Verifying the Home Depot cart subtotal…");
  await new Promise((resolve) => setTimeout(resolve, 1800));
  const bodyText = String(document.body?.innerText || "");
  if (/there['’]s nothing in here yet/i.test(bodyText)) {
    const reason = "Checkout blocked: Home Depot did not add the approved item to the cart.";
    await autozsMarkCheckoutReview(supplierOrderId, reason);
    autozsCheckoutProgress(100, reason, "error");
    return;
  }
  const cartSubtotal = autozsCartPayableSubtotal(bodyText);
  const expectedSubtotal = autozsExpectedSupplierSubtotal(supplierOrder);
  if (autozsCheckoutPriceMismatch(expectedSubtotal, cartSubtotal)) {
    const alreadyRebuilt = sessionStorage.getItem(AUTOZS_CHECKOUT_CART_REBUILD_KEY) === String(supplierOrderId);
    if (!alreadyRebuilt && cartSubtotal !== null && cartSubtotal > expectedSubtotal) {
      autozsCheckoutProgress(76, "Removing stale items from the dedicated checkout cart…");
      let removed = 0;
      for (let attempt = 0; attempt < 12; attempt += 1) {
        if (!autozsFindButton(/^remove$/i)) break;
        try {
          await autozsNativeCheckoutClick(supplierOrderId, "remove_from_cart");
          removed += 1;
        } catch (error) {
          let visiblyEmpty = false;
          for (let settle = 0; settle < 10; settle += 1) {
            await new Promise((resolve) => setTimeout(resolve, 500));
            visiblyEmpty = /there['â€™]s nothing in here yet/i.test(String(document.body?.innerText || ""));
            if (visiblyEmpty) break;
          }
          if (visiblyEmpty) break;
          throw error;
        }
        await new Promise((resolve) => setTimeout(resolve, 650));
      }
      if (removed > 0 && /there['’]s nothing in here yet/i.test(String(document.body?.innerText || ""))) {
        const sourceUrl = supplierOrder.items?.[0]?.source_url || supplierOrder.source_url;
        const productUrl = new URL(sourceUrl || "");
        if (productUrl.hostname === "www.homedepot.com" && /^\/p\//i.test(productUrl.pathname)) {
          sessionStorage.setItem(AUTOZS_CHECKOUT_CART_REBUILD_KEY, String(supplierOrderId));
          productUrl.searchParams.set("autozs_supplier_order", String(supplierOrderId));
          productUrl.searchParams.set("autozs_checkout_canary", "1");
          location.assign(productUrl.href);
          return;
        }
      }
    }
    const reason = `Checkout blocked: Home Depot cart subtotal is ${cartSubtotal === null ? "unreadable" : `$${cartSubtotal.toFixed(2)}`}; approved subtotal is $${expectedSubtotal.toFixed(2)}.`;
    await autozsMarkCheckoutReview(supplierOrderId, reason, cartSubtotal === null ? {} : { item_subtotal: cartSubtotal, total: cartSubtotal });
    autozsCheckoutProgress(100, reason, "error");
    return;
  }
  autozsCheckoutProgress(79, "Confirming free delivery in the cartâ€¦");
  const cartHasConfirmedDelivery = () => {
    const orderSummary = String(document.body?.innerText || "").split(/Your Order/i).slice(-1)[0];
    return /Delivery\s+FREE/i.test(orderSummary) && !/Pickup\s+FREE/i.test(orderSummary.slice(0, 500));
  };
  let cartDeliveryConfirmed = cartHasConfirmedDelivery();
  if (!cartDeliveryConfirmed) await autozsNativeCheckoutClick(supplierOrderId, "delivery");
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    cartDeliveryConfirmed = cartHasConfirmedDelivery();
    if (cartDeliveryConfirmed) break;
  }
  if (!cartDeliveryConfirmed) {
    const reason = "Checkout blocked: Home Depot did not confirm free delivery in the cart; pickup checkout was not allowed.";
    await autozsMarkCheckoutReview(supplierOrderId, reason);
    autozsCheckoutProgress(100, reason, "error");
    return;
  }
  sessionStorage.removeItem(AUTOZS_CHECKOUT_CART_REBUILD_KEY);
  const checkout = autozsFindButton(/^(secure )?checkout$/i) || autozsFindButton(/proceed to checkout/i);
  if (!checkout) {
    const reason = "Checkout paused: the cart is correct, but Home Depot's Checkout button was not found.";
    await autozsMarkCheckoutReview(supplierOrderId, reason);
    autozsCheckoutProgress(100, reason, "error");
    return;
  }
  sessionStorage.setItem(AUTOZS_CHECKOUT_SESSION_KEY, String(supplierOrderId));
  autozsCheckoutProgress(82, "Cart verified. Opening Home Depot's checkout form…");
  await autozsNativeCheckoutClick(supplierOrderId, "checkout");
}

async function autozsRunCheckoutReview(supplierOrderId, supplierOrder) {
  autozsCheckoutProgress(84, "Entering and verifying the eBay shipping address…");
  await new Promise((resolve) => setTimeout(resolve, 1800));
  const names = autozsSplitCheckoutName(supplierOrder.recipient_name);
  const readRequiredFields = () => ({
    firstName: autozsCheckoutField(['input[name*="firstName" i]', 'input[id*="firstName" i]', 'input[autocomplete="given-name"]']),
    lastName: autozsCheckoutField(['input[name*="lastName" i]', 'input[id*="lastName" i]', 'input[autocomplete="family-name"]']),
    address1: autozsCheckoutField(['input[name*="addressLine1" i]', 'input[name="line1" i]', 'input[name="address1" i]', 'input[autocomplete="address-line1"]']),
    postal: autozsCheckoutField(['input[name*="postal" i]', 'input[name*="zip" i]', 'input[autocomplete="postal-code"]']),
  });
  let requiredFields = readRequiredFields();
  if (Object.values(requiredFields).some((field) => !field)) {
    const savedAddress = autozsCheckoutAddressText(document.body?.innerText || "");
    const expectedParts = [supplierOrder.recipient_name, supplierOrder.address_line1, supplierOrder.city, supplierOrder.state, String(supplierOrder.postal_code || "").slice(0, 5)]
      .map(autozsCheckoutAddressText)
      .filter(Boolean);
    if (!expectedParts.every((part) => savedAddress.includes(part))) {
      throw new Error("Home Depot's required delivery-address fields were not found.");
    }
    await autozsNativeCheckoutClick(supplierOrderId, "edit_address");
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      requiredFields = readRequiredFields();
      if (Object.values(requiredFields).every(Boolean)) break;
    }
    if (Object.values(requiredFields).some((field) => !field)) throw new Error("Home Depot did not reopen its saved delivery address for verification.");
  }
  await autozsNativeCheckoutFill(supplierOrderId, "first_name", names.firstName);
  await autozsNativeCheckoutFill(supplierOrderId, "last_name", names.lastName);
  await autozsNativeCheckoutFill(supplierOrderId, "address1", supplierOrder.address_line1);
  const address2 = autozsCheckoutField(['input[name*="addressLine2" i]', 'input[name="line2" i]', 'input[name="address2" i]', 'input[autocomplete="address-line2"]']);
  if (address2 && supplierOrder.address_line2) {
    await autozsNativeCheckoutFill(supplierOrderId, "address2", supplierOrder.address_line2);
  }
  const phone = autozsCheckoutField(['input[autocomplete="tel"]', 'input[name*="phone" i]', 'input[type="tel"]']);
  if (!phone) throw new Error("Home Depot's seller notification phone field was not found.");
  await autozsNativeCheckoutFill(supplierOrderId, "phone", supplierOrder.phone);
  const checkoutPostal = String(supplierOrder.postal_code || "").replace(/\D/g, "").slice(0, 5);
  if (checkoutPostal.length !== 5) throw new Error("The eBay shipping ZIP code is invalid.");
  await autozsNativeCheckoutFill(supplierOrderId, "postal", checkoutPostal);
  // Home Depot may restore the signed-in account's saved city after the other
  // address fields settle. Re-commit ZIP once so its live city resolver wins.
  await new Promise((resolve) => setTimeout(resolve, 750));
  await autozsNativeCheckoutFill(supplierOrderId, "postal", checkoutPostal);
  let fields = {};
  let lastStaticCityState = null;
  for (let attempt = 0; attempt < 16; attempt += 1) {
    fields.city = autozsCheckoutField(['select[name*="city" i]', 'input[name*="city" i]', 'input[autocomplete="address-level2"]']);
    fields.state = autozsCheckoutField(['select[name*="state" i]', 'input[name*="state" i]', '[autocomplete="address-level1"]']);
    const staticCityState = autozsCheckoutStaticCityState(document.body?.innerText || "");
    lastStaticCityState = staticCityState || lastStaticCityState;
    const staticMatchesExpected = staticCityState
      && autozsCheckoutAddressText(staticCityState.city) === autozsCheckoutAddressText(supplierOrder.city)
      && autozsCheckoutAddressText(staticCityState.state) === autozsCheckoutAddressText(supplierOrder.state);
    if (!fields.city && staticMatchesExpected) fields.city = { value: staticCityState.city };
    if (!fields.state && staticMatchesExpected) fields.state = { value: staticCityState.state };
    if (fields.city && fields.state) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (!fields.city || !fields.state) {
    const observed = lastStaticCityState ? ` It last showed ${lastStaticCityState.city}, ${lastStaticCityState.state}.` : "";
    throw new Error(`Home Depot did not resolve the ZIP code to the eBay city/state.${observed}`);
  }
  if (!fields.city.tagName && !fields.state.tagName) {
    if (autozsCheckoutAddressText(fields.city.value) !== autozsCheckoutAddressText(supplierOrder.city)
      || autozsCheckoutAddressText(fields.state.value) !== autozsCheckoutAddressText(supplierOrder.state)) {
      throw new Error(`Home Depot resolved the ZIP code to ${fields.city.value}, ${fields.state.value}, not the eBay city/state.`);
    }
  } else if (fields.city.tagName === "SELECT") {
    const choices = [...fields.city.options].map((option) => ({ city: option.textContent, state: supplierOrder.state, value: option.value, option }));
    const choice = autozsChooseCheckoutCity(choices, supplierOrder.city, supplierOrder.state);
    if (!choice) throw new Error(`Home Depot did not provide one exact ${supplierOrder.city}, ${supplierOrder.state} city choice for this ZIP code.`);
    autozsSetNativeInputValue(fields.city, choice.value);
  } else await autozsNativeCheckoutFill(supplierOrderId, "city", supplierOrder.city);
  if (fields.state.tagName === "SELECT") autozsSetNativeInputValue(fields.state, supplierOrder.state);
  else if (fields.state.tagName) await autozsNativeCheckoutFill(supplierOrderId, "state", supplierOrder.state);
  fields = {
    firstName: autozsCheckoutField(['input[autocomplete="given-name"]', 'input[name*="firstName" i]']),
    lastName: autozsCheckoutField(['input[autocomplete="family-name"]', 'input[name*="lastName" i]']),
    address1: autozsCheckoutField(['input[autocomplete="address-line1"]', 'input[name="line1" i]']),
    address2,
    postal: autozsCheckoutField(['input[autocomplete="postal-code"]', 'input[name*="zip" i]']),
    city: fields.city,
    state: fields.state,
  };
  if (!autozsCheckoutAddressMatches(supplierOrder, autozsCheckoutObservedAddress(fields))) {
    throw new Error("Home Depot's address read-back does not exactly match the eBay shipping address.");
  }

  autozsCheckoutProgress(89, "Address verified. Opening delivery options…");
  await autozsNativeCheckoutClick(supplierOrderId, "continue");
  let paymentReady = false;
  let deliveryContinueClicked = false;
  let deliveryContinueReady = false;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const newCardField = autozsCheckoutField([
      'input[autocomplete="cc-number"]',
      'input[name*="cardNumber" i]',
      'input[id*="cardNumber" i]',
    ]);
    const checkoutBody = String(document.body?.innerText || "");
    paymentReady = Boolean(newCardField) || /Payment Method[\s\S]{0,500}\*{4}\s*\d{4}/i.test(checkoutBody);
    if (paymentReady) break;
    const deliveryContinue = [...document.querySelectorAll('button[name="DeliveryOptionsContinueButton"],button[data-automation-id="DeliveryOptionsContinueButton"]')]
      .find((button) => button.offsetParent !== null) || null;
    const deliveryText = String(document.body?.innerText || "");
    const deliveryState = autozsCheckoutDeliveryState(deliveryText, Boolean(deliveryContinue), deliveryContinue?.disabled);
    if (deliveryState.enabled && !deliveryContinueClicked) {
      deliveryContinueReady = true;
      if (deliveryState.free) {
        autozsCheckoutProgress(90, "Free delivery verified. Opening payment…");
        await autozsNativeCheckoutClick(supplierOrderId, "delivery_continue");
        deliveryContinueClicked = true;
      }
    } else if (deliveryState.visible && !deliveryState.enabled && deliveryState.unavailable) {
      throw new Error("Home Depot cannot provide the approved free delivery option to this address.");
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (!paymentReady) {
    if (deliveryContinueReady && !deliveryContinueClicked) {
      throw new Error("Home Depot enabled delivery, but its cost was not verified as free.");
    }
    throw new Error("Home Depot kept the address stage open after Continue; payment was not accessed.");
  }

  autozsCheckoutProgress(91, "Address and delivery verified. Filling the secured payment card…");
  const credential = await autozsCheckoutCredential(supplierOrderId);
  let cardNumberField = autozsCheckoutField(['input[autocomplete="cc-number"]', 'input[name*="cardNumber" i]', 'input[id*="cardNumber" i]']);
  const lastFour = String(credential.card_number || "").replace(/\D/g, "").slice(-4);
  if (!cardNumberField && (!lastFour || !String(document.body?.innerText || "").includes(`****${lastFour}`))) {
    await autozsNativeCheckoutClick(supplierOrderId, "add_new_card");
    let secureCardFramesReady = false;
    for (let attempt = 0; attempt < 20 && !cardNumberField && !secureCardFramesReady; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      cardNumberField = autozsCheckoutField(['input[autocomplete="cc-number"]', 'input[name*="cardNumber" i]', 'input[id*="cardNumber" i]']);
      secureCardFramesReady = Boolean(document.querySelector('iframe#iframe-credit-card-payment-field,iframe[title="card_sdk"]'));
    }
    if (!cardNumberField && !secureCardFramesReady) throw new Error("Home Depot did not open its approved-card entry form.");
  }
  const secureCardFramesReady = Boolean(document.querySelector('iframe#iframe-credit-card-payment-field,iframe[title="card_sdk"]'));
  if (cardNumberField || secureCardFramesReady) {
    await autozsNativeCheckoutFill(supplierOrderId, "card_number", credential.card_number);
    if (secureCardFramesReady) {
      const billingPostal = String(credential.billing_postal_code || "").replace(/\D/g, "").slice(0, 5);
      const checkoutDigits = String(document.body?.innerText || "").replace(/\D/g, "");
      if (!billingPostal || !checkoutDigits.includes(billingPostal)) {
        throw new Error("Home Depot's displayed billing address does not match the approved card postal code.");
      }
      await autozsNativeCheckoutFill(supplierOrderId, "expiration", `${String(credential.expiration_month).padStart(2, "0")}/${String(credential.expiration_year).slice(-2)}`);
      await autozsNativeCheckoutFill(supplierOrderId, "security_code", credential.security_code);
      await new Promise((resolve) => setTimeout(resolve, 800));
      await autozsNativeCheckoutClick(supplierOrderId, "use_new_card");
      for (let attempt = 0; attempt < 20 && !String(document.body?.innerText || "").includes(`****${lastFour}`); attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      if (!lastFour || !String(document.body?.innerText || "").includes(`****${lastFour}`)) {
        throw new Error("Home Depot did not select the approved checkout card after secured entry.");
      }
    } else {
      await autozsNativeCheckoutFill(supplierOrderId, "cardholder", credential.cardholder_name);
      await autozsNativeCheckoutFill(supplierOrderId, "expiration_month", String(credential.expiration_month).padStart(2, "0"));
      await autozsNativeCheckoutFill(supplierOrderId, "expiration_year", String(credential.expiration_year));
      await autozsNativeCheckoutFill(supplierOrderId, "security_code", credential.security_code);
      await autozsNativeCheckoutFill(supplierOrderId, "billing_postal", credential.billing_postal_code);
    }
  } else {
    if (!lastFour || !String(document.body?.innerText || "").includes(`****${lastFour}`)) {
      throw new Error("Home Depot's selected saved card does not match the approved checkout card.");
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 1200));

  const totals = autozsCheckoutTotals(document.body?.innerText || "");
  const expectedSubtotal = autozsExpectedSupplierSubtotal(supplierOrder);
  if (!autozsCheckoutTotalsAreSafe(totals, expectedSubtotal, credential.approved_total)) {
    throw new Error(`Home Depot's final total could not be verified within the approved $${Number(credential.approved_total).toFixed(2)} ceiling.`);
  }
  const reason = `Ready for owner review: Home Depot address, seller phone, payment, and $${totals.total.toFixed(2)} final total were verified. AUTOZS did not click Place order.`;
  await autozsMarkCheckoutReview(supplierOrderId, reason, {
    item_subtotal: totals.subtotal, shipping_cost: totals.shipping, sales_tax: totals.tax,
    card_amount: totals.total, total: totals.total,
  });
  autozsCheckoutProgress(100, reason, "complete");
}

function autozsHomeDepotCheckoutErrorPage(title = document.title, bodyText = document.body?.innerText || "") {
  const heading = String(title || "").trim();
  const body = String(bodyText || "");
  return /^error page$/i.test(heading)
    || /we're sorry.{0,80}(?:technical|unexpected|went wrong)/is.test(body)
    || /temporarily unavailable.{0,80}(?:cart|checkout)/is.test(body);
}

async function autozsStartSupplierCheckout() {
  if (await autozsObserveHomeDepotTrackingBounded()) return;
  const params = new URLSearchParams(location.search);
  const supplierOrderId = Number(params.get("autozs_supplier_order") || sessionStorage.getItem(AUTOZS_CHECKOUT_SESSION_KEY));
  if (!supplierOrderId || (params.get("autozs_checkout_canary") !== "1" && !sessionStorage.getItem(AUTOZS_CHECKOUT_SESSION_KEY))) return;
  // Home Depot removes the cart query string when it opens /checkout. Restore
  // only the session-bound guarded identity so background API and input
  // allow-lists continue to recognize this same claimed order and tab.
  if (!params.get("autozs_supplier_order") && /checkout/i.test(location.pathname)) {
    const guardedUrl = new URL(location.href);
    guardedUrl.searchParams.set("autozs_supplier_order", String(supplierOrderId));
    guardedUrl.searchParams.set("autozs_checkout_canary", "1");
    history.replaceState(history.state, "", guardedUrl.href);
  }
  autozsCheckoutProgress(10, `Loading supplier order #${supplierOrderId}…`);
  try {
    if (autozsHomeDepotCheckoutErrorPage()) {
      throw new Error("Home Depot returned its server-side Error Page. Checkout is cooling down for 30 minutes before another guarded attempt.");
    }
    const supplierOrder = await autozsCheckoutApi(`/supplier-orders/${supplierOrderId}`);
    if (await autozsReconcileHomeDepotConfirmation(supplierOrderId, supplierOrder)) return;
    if (supplierOrder.status !== "placing") {
      autozsCheckoutProgress(100, `Supplier order #${supplierOrderId} is ${supplierOrder.status}; checkout did not run.`, "error");
      return;
    }
    if (supplierOrder.supplier !== "home_depot" || supplierOrder.items?.length !== 1) {
      const reason = "Checkout blocked: the first canary only supports one Home Depot item per supplier order.";
      await autozsMarkCheckoutReview(supplierOrderId, reason);
      autozsCheckoutProgress(100, reason, "error");
      return;
    }
    if (/^\/p\//i.test(location.pathname)) {
      await autozsRunProductCheckoutCanary(supplierOrderId, supplierOrder);
      return;
    }
    if (/\/(?:mycart(?:\/|$)|cart(?:\/|$))/i.test(location.pathname)) {
      await autozsRunCartCheckoutCanary(supplierOrderId, supplierOrder);
      return;
    }
    if (/checkout/i.test(location.pathname)) {
      await autozsRunCheckoutReview(supplierOrderId, supplierOrder);
      return;
    }
    const reason = `Checkout paused on an unsupported Home Depot step (${location.pathname}).`;
    await autozsMarkCheckoutReview(supplierOrderId, reason);
    autozsCheckoutProgress(100, reason, "error");
  } catch (error) {
    const reason = `Checkout paused safely: ${error.message || String(error)}`;
    try { await autozsMarkCheckoutReview(supplierOrderId, reason); } catch {}
    autozsCheckoutProgress(100, reason, "error");
  }
}

let autozsSupplierCheckoutRunPromise = null;

function autozsEnsureSupplierCheckoutStarted() {
  if (autozsSupplierCheckoutRunPromise) return autozsSupplierCheckoutRunPromise;
  autozsSupplierCheckoutRunPromise = autozsStartSupplierCheckout()
    .finally(() => { autozsSupplierCheckoutRunPromise = null; });
  return autozsSupplierCheckoutRunPromise;
}

if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "autozs-supplier-checkout-ping") {
      sendResponse({ ok: true, ready: true, running: Boolean(autozsSupplierCheckoutRunPromise) });
      return false;
    }
    if (message?.type === "autozs-supplier-checkout-start") {
      autozsEnsureSupplierCheckoutStarted().catch(() => {});
      sendResponse({ ok: true, started: true });
      return false;
    }
    return undefined;
  });
}

if (typeof location !== "undefined" && location.hostname === "www.homedepot.com") {
  autozsEnsureSupplierCheckoutStarted();
}
