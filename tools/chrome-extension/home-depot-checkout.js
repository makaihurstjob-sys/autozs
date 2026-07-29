var AUTOZS_CHECKOUT_API = "https://desktop-56u49jf.tailb2892a.ts.net:8443";
var AUTOZS_CHECKOUT_BUILD = "2026-07-28-guarded-cart-canary";

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

function autozsCheckoutOverlay() {
  let host = document.getElementById("autozs-supplier-checkout-overlay");
  if (host) return host;
  host = document.createElement("div");
  host.id = "autozs-supplier-checkout-overlay";
  host.style.cssText = [
    "position:fixed", "inset:0", "z-index:2147483647", "background:rgba(6,14,11,.80)",
    "display:flex", "align-items:center", "justify-content:center", "font-family:Arial,sans-serif",
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

function autozsSetNativeInputValue(input, value) {
  const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value");
  descriptor?.set?.call(input, String(value));
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function autozsFindButton(pattern) {
  return [...document.querySelectorAll("button")].find((button) =>
    !button.disabled && pattern.test(String(button.innerText || button.textContent || "").trim())
  );
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
  const deliveryButton = autozsFindButton(/^delivery\b/i);
  deliveryButton?.click();
  const quantityInput = document.querySelector(
    'input[name*="quantity" i], input[aria-label*="quantity" i], input[data-testid*="quantity" i]'
  );
  if (quantityInput) autozsSetNativeInputValue(quantityInput, requestedQuantity);
  const addToCart = autozsFindButton(/^add to cart$/i);
  if (!addToCart) {
    const reason = "Checkout paused: AutoZS verified the price but could not find Home Depot's Add to Cart button.";
    await autozsMarkCheckoutReview(supplierOrderId, reason);
    autozsCheckoutProgress(100, reason, "error");
    return;
  }
  autozsCheckoutProgress(68, "Adding the verified item to the cart…");
  addToCart.click();
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
  const subtotalMatch = bodyText.match(/\bsubtotal\b[\s\S]{0,90}?(\$\s*[0-9]{1,5}(?:,[0-9]{3})*(?:\.[0-9]{2})?)/i);
  const cartSubtotal = autozsCheckoutMoney(subtotalMatch?.[1]);
  const expectedSubtotal = autozsExpectedSupplierSubtotal(supplierOrder);
  if (autozsCheckoutPriceMismatch(expectedSubtotal, cartSubtotal)) {
    const reason = `Checkout blocked: Home Depot cart subtotal is ${cartSubtotal === null ? "unreadable" : `$${cartSubtotal.toFixed(2)}`}; approved subtotal is $${expectedSubtotal.toFixed(2)}.`;
    await autozsMarkCheckoutReview(supplierOrderId, reason, cartSubtotal === null ? {} : { item_subtotal: cartSubtotal, total: cartSubtotal });
    autozsCheckoutProgress(100, reason, "error");
    return;
  }
  const reason = `Checkout canary reached the cart with a verified $${cartSubtotal.toFixed(2)} subtotal. Final checkout, tax, address, gift-card application, and Place order remain disabled pending the next guarded test.`;
  await autozsMarkCheckoutReview(supplierOrderId, reason, { item_subtotal: cartSubtotal, total: cartSubtotal });
  autozsCheckoutProgress(100, reason, "complete");
}

async function autozsStartSupplierCheckout() {
  const params = new URLSearchParams(location.search);
  const supplierOrderId = Number(params.get("autozs_supplier_order"));
  if (!supplierOrderId || params.get("autozs_checkout_canary") !== "1") return;
  autozsCheckoutProgress(10, `Loading supplier order #${supplierOrderId}…`);
  try {
    const supplierOrder = await autozsCheckoutApi(`/supplier-orders/${supplierOrderId}`);
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
    if (/\/mycart\//i.test(location.pathname)) {
      await autozsRunCartCheckoutCanary(supplierOrderId, supplierOrder);
      return;
    }
    const reason = `Checkout paused on an unsupported Home Depot step (${location.pathname}).`;
    await autozsMarkCheckoutReview(supplierOrderId, reason);
    autozsCheckoutProgress(100, reason, "error");
  } catch (error) {
    autozsCheckoutProgress(100, `Checkout canary stopped: ${error.message || String(error)}`, "error");
  }
}

if (typeof location !== "undefined" && location.hostname === "www.homedepot.com") {
  autozsStartSupplierCheckout();
}
