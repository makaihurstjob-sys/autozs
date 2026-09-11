// Read-only observer: never adds/removes items, changes destinations or enters checkout.
function autozsReadDeliveryQuote(doc) {
  const rows = [...doc.querySelectorAll('[data-testid="cart-item"], [data-testid="cartItem"], .cart-item')];
  if (rows.length !== 1) return null; // Order-level shipping cannot be attributed in a mixed cart.
  const row = rows[0];
  const urls = [...new Set([...row.querySelectorAll('a[href*="/p/"]')].map(link => {
    try {
      const url = new URL(link.href);
      return url.origin === 'https://www.homedepot.com' && /^\/p\/[^/]+\/\d+\/?$/.test(url.pathname)
        ? url.origin + url.pathname : '';
    } catch { return ''; }
  }))];
  if (urls.length !== 1 || !urls[0]) return null;
  const inputs = row.querySelectorAll('input[name*="quantity" i], input[aria-label*="quantity" i], select[aria-label*="quantity" i]');
  if (inputs.length !== 1 || !/^[1-9]\d{0,2}$/.test(String(inputs[0].value))) return null;
  const text = String(doc.body?.innerText || '');
  if (/updating|loading|out of stock|unavailable|not available/i.test(text)) return null;
  const destinations = [...text.matchAll(/Delivering to\s+(\d{5})(?:-\d{4})?\b/gi)].map(m => m[1]);
  if (!destinations.length || destinations.some(zip => zip !== destinations[0])) return null;
  const parts = text.split(/Your Order/i);
  if (parts.length !== 2 || /\bPickup\b/i.test(parts[1])) return null;
  const charges = [...parts[1].matchAll(/\bDelivery\s+(FREE|\$\s*\d+(?:,\d{3})*(?:\.\d{2})?)(?=\s|$)/gi)];
  if (charges.length !== 1) return null;
  const amount = /^FREE$/i.test(charges[0][1]) ? 0 : Number(charges[0][1].replace(/[$,\s]/g, ''));
  if (!Number.isFinite(amount)) return null;
  return { source_url: urls[0], postal_code: destinations[0], quantity: Number(inputs[0].value), delivery_charge: amount };
}

if (typeof location !== 'undefined' && ['/mycart/home', '/cart'].includes(location.pathname)
    && chrome.runtime.getManifest().name !== 'AutoZS Isolated Delivery Checks'
    && !globalThis.autozsCartQuoteObserverStarted) {
  globalThis.autozsCartQuoteObserverStarted = true;
  let previous = '', saved = '', pending = false;
  setInterval(() => {
    const quote = autozsReadDeliveryQuote(document);
    const key = quote ? JSON.stringify(quote) : '';
    if (key && key === previous && key !== saved && !pending) {
      pending = true;
      chrome.runtime.sendMessage({ type: 'autozs-cart-delivery-quote', quote }, response => {
        pending = false;
        if (!chrome.runtime.lastError && response?.ok) saved = key;
      });
    }
    previous = key;
  }, 3000);
}
