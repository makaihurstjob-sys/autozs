/* Injected only by the isolated extension. All controls are exact and unique. */
function autozsDeliveryPage(action, job) {
  const visible = el => !!el && !el.disabled && el.getClientRects().length > 0;
  const buttons = root => [...root.querySelectorAll('button, [role="button"], a')].filter(visible);
  const label = el => String(el.innerText || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
  const unique = (items, pattern) => {
    const matches = items.filter(el => pattern.test(label(el)));
    if (matches.length !== 1) throw Error('Delivery control is missing or ambiguous');
    return matches[0];
  };
  if (location.origin !== 'https://www.homedepot.com' ||
      !(['/mycart/home', '/cart'].includes(location.pathname) || /^\/p\/[^/]+\/\d+\/?$/.test(location.pathname))) {
    throw Error('Delivery checks cannot run on this page');
  }
  const text = String(document.body?.innerText || '');
  if (/oops[!\s]*something went wrong|please refresh page/i.test(text) || document.title === 'Error Page') {
    throw Error('Transient supplier page error: Home Depot requested a refresh');
  }
  if (/verify you are human|pardon our dust|access denied|verify your identity/i.test(text)) throw Error('Browser verification requires review');
  const allButtons = buttons(document);
  // Do not use a signed-in cart, even in the dedicated profile.
  const guest = allButtons.some(el => /^(sign in|sign in to your account|log in|log in to your account)$/i.test(label(el)));
  if (!guest) throw Error('Signed-out guest session could not be verified');
  const rows = [...document.querySelectorAll('[data-testid="cart-item"], [data-testid="cartItem"], .cart-item')];
  const productId = value => {
    try { const url = new URL(value); return url.origin === location.origin ? url.pathname.match(/^\/p\/[^/]+\/(\d+)\/?$/)?.[1] : null; }
    catch { return null; }
  };
  const expectedId = productId(job.source_url);
  const cartMatches = () => {
    if (rows.length !== 1) return false;
    const ids = [...new Set([...rows[0].querySelectorAll('a[href*="/p/"]')].map(a => productId(a.href)))];
    const quantities = [...rows[0].querySelectorAll('input[name*="quantity" i], input[aria-label*="quantity" i], select[aria-label*="quantity" i]')];
    return ids.length === 1 && ids[0] === expectedId && quantities.length === 1 && String(quantities[0].value) === '1';
  };
  const empty = rows.length === 0 && /(?:your cart is empty|there['’]s nothing in here yet)/i.test(text);
  const setValue = (input, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  };
  if (action === 'inspect') {
    const quote = ['/mycart/home', '/cart'].includes(location.pathname) && cartMatches() ? autozsReadDeliveryQuote(document) : null;
    return { empty, cartMatches: cartMatches(), quote, path: location.pathname };
  }
  if (action === 'prepare_product' || action === 'add') {
    if (productId(location.href) !== expectedId) throw Error('Wrong product page');
    const count = document.querySelector('[data-testid="header-cart-count"]');
    if (!count || String(count.textContent).trim() !== '0') throw Error('Cannot confirm an empty cart before adding');
    if (action === 'prepare_product') {
      // Fulfillment selection is the exact Delivery control, not delivery
      // details/help links or a Delivering to ZIP control. Never pick the first match.
      const delivery = unique(allButtons, /^delivery$/i);
      const quantities = [...document.querySelectorAll('input[name*="quantity" i], input[aria-label*="quantity" i]')].filter(visible);
      if (quantities.length !== 1) throw Error('Product quantity is ambiguous');
      delivery.click();
      setValue(quantities[0], '1');
      return { prepared: true };
    }
    const quantities = [...document.querySelectorAll('input[name*="quantity" i], input[aria-label*="quantity" i]')].filter(visible);
    if (quantities.length !== 1 || quantities[0].value !== '1') throw Error('Product quantity changed');
    unique(allButtons, /^add to cart$/i).click();
    return { added: true };
  }
  if (!['/mycart/home', '/cart'].includes(location.pathname) || !cartMatches()) throw Error('Cart identity or quantity is ambiguous; preserved for review');
  if (action === 'zip') {
    const dialogs = [...document.querySelectorAll('[role="dialog"], dialog')].filter(visible);
    const inputs = dialogs.flatMap(root => [...root.querySelectorAll('input[autocomplete="postal-code"], input[name*="zip" i], input[id*="zip" i]')].filter(visible));
    if (dialogs.length === 1 && inputs.length === 1) {
      setValue(inputs[0], job.postal_code);
      unique(buttons(dialogs[0]), /^(apply|save|update|submit|save zip code|update zip code)$/i).click();
    } else if (!dialogs.length) {
      unique(allButtons, /^(?:Delivering to\s+\d{5}(?:-\d{4})?|change (?:delivery )?zip(?: code)?|edit (?:delivery )?zip(?: code)?)$/i).click();
    } else throw Error('ZIP dialog is ambiguous');
    return { changed: true };
  }
  if (action === 'remove') {
    unique(buttons(rows[0]), /^remove$/i).click();
    return { removed: true };
  }
  throw Error('Unsupported delivery-check action');
}
