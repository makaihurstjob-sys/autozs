// Fail closed: report metadata and generic shipping instructions are not evidence.
function classifyEbayOrderSnapshot(snapshot, expected) {
  const text = String(snapshot?.text || "").replace(/\s+/g, " ").trim();
  let url;
  try { url = new URL(snapshot.url); } catch { return { status: "unknown", evidence: "Invalid page URL" }; }
  const account = text.match(/Seller Hub\s+(\S+)\s+View profile/i)?.[1] || "";
  const exactOrder = text.includes(`Order ${expected.ebay_order_id}`);
  if (url.origin !== "https://www.ebay.com" || url.pathname !== "/mesh/ord/details"
      || url.searchParams.get("orderid") !== expected.ebay_order_id
      || account !== expected.account_key || !exactOrder || snapshot.readyState !== "complete") {
    return { status: "unknown", evidence: "Exact loaded order/account identity was not verified" };
  }
  const details = text.split("Order details")[1] || "";
  const header = details.split(/Shipping instructions|Ship to/)[0];
  const evidence = header.slice(0, 1800);
  if (/cancel(?:led|ed|lation)|cancel(?:lation)? requested|request to cancel/i.test(header)
      || /cancellation (?:requested|pending|in progress)|request to cancel|this order was cancel/i.test(details)) return { status: "cancelled", evidence };
  if (/refund|return requested|payment dispute|chargeback/i.test(details)) return { status: "refunded", evidence: "Refund/return/dispute indicator on exact order. " + evidence };
  if (/\bshipped\b|\bdelivered\b|label created|\bin transit\b/i.test(header)) return { status: "fulfilled", evidence };
  // An existing shipment anywhere in the order details must hold checkout.
  if (/Tracking\s+[A-Z0-9]{8,}/i.test(details)) return { status: "fulfilled", evidence: "Tracking already recorded. " + evidence };
  const trackingEmpty = /Tracking\s+--\s+Add tracking\b/i.test(details);
  const paid = /Buyer paid\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b/i.test(header);
  if (paid && /\bShip by\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b/i.test(header)
      && trackingEmpty && !/awaiting payment|unpaid|payment pending|on hold.*payment/i.test(header)) {
    return { status: "eligible", evidence };
  }
  return { status: "unknown", evidence: evidence || "Order status could not be read" };
}

async function verifyLiveEbaySupplierOrder(expected) {
  if (!expected?.supplier_order_id || !expected.ebay_order_id || !expected.account_key) throw new Error("Missing eBay verification identity.");
  const url = `https://www.ebay.com/mesh/ord/details?mode=SH&orderid=${encodeURIComponent(expected.ebay_order_id)}`;
  const tab = await chrome.tabs.create({ url, active: false });
  let observation = { status: "unknown", evidence: "eBay detail page did not load in time" };
  try {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 750));
      try {
        const results = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => ({
          url: location.href, readyState: document.readyState, text: document.body?.innerText || "",
        }) });
        observation = classifyEbayOrderSnapshot(results[0]?.result, expected);
        if (observation.status !== "unknown") break;
      } catch { /* Loading/navigation errors remain unverified. */ }
    }
    const response = await fetch(`${LOCAL_CHECKOUT_API}/supplier-orders/${expected.supplier_order_id}/ebay-verification`, {
      headers: { "Content-Type": "application/json" }, cache: "no-store",
      method: "POST", body: JSON.stringify({
        ebay_order_id: expected.ebay_order_id, account_key: expected.account_key,
        source_url: url, observed_at: new Date().toISOString(), ...observation,
      }),
    });
    if (!response.ok) throw new Error(`eBay evidence persistence failed (${response.status}); checkout held.`);
    if (observation.status !== "eligible") throw new Error(`Live eBay verification held checkout: ${observation.status}.`);
    return observation;
  } finally {
    try { await chrome.tabs.remove(tab.id); } catch { /* Owner may have closed it. */ }
  }
}
