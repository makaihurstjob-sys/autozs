(async()=>{if(await hasRunningListingJob())throw Error('Running job');const t=(await chrome.tabs.query({url:'https://www.ebay.com/lstng*'}))[0];return chrome.scripting.executeScript({target:{tabId:t.id},func:async()=>{try{async function revealEbayItemSpecifics() {
  const heading = [...document.querySelectorAll('h2, h3, [role="heading"]')]
    .find((element) => /^item specifics$/i.test(String(element.innerText || element.textContent || '').trim()));
  if (!heading) return true;
  heading.scrollIntoView?.({block:'center', inline:'nearest'});
  return waitForCondition(() => ebayItemSpecificRows().length > 0, 5000, 150);
}
function requiredItemSpecificsSatisfied() {
  const rows = ebayItemSpecificRows();
  const heading = [...document.querySelectorAll('h2, h3, [role="heading"]')]
    .find((element) => /^item specifics$/i.test(String(element.innerText || element.textContent || '').trim()));
  if (heading && !rows.length) return false;
  if (rows.some((row) => row.required && !ebayItemSpecificRowValue(row))) return false;
  const text = document.body?.innerText || "";
  const validationBanner = /looks like something is missing or invalid/i.test(text) && /item specifics/i.test(text);
  return !validationBanner && !/additional details are required|item specific\s+[^.\n]+\s+is missing/i.test(text);
}
function ebayItemSpecificRowValue(row) {
  if (!row?.valueHost) return "";
  const picked = [...row.valueHost.querySelectorAll('button[name^="attributes."]')]
    .map((button) => String(button.innerText || "").trim())
    .filter((text) => text && !/^clear$/i.test(text));
  if (picked.length) return picked.join(", ");
  const input = row.valueHost.querySelector('input[type="text"]');
  if (input && /search-box|extracted-attribute-selector/i.test(input.getAttribute?.("name") || "")) return "";
  return input ? String(input.value || "").trim() : "";
}
async function fillRequiredEbayItemSpecifics(pkg) {
  const filled = [];
  const titleWords = normalizeComparableValue(pkg?.title || "").split(/\s+/).filter((word) => word.length > 3);
  for (const row of ebayItemSpecificRows()) {
    if (!row.required || ebayItemSpecificRowValue(row)) continue;
    const supplied = inferredItemSpecifics(pkg)[row.key];
    const preferred = [supplied, ...titleWords].filter(Boolean);
    if (await chooseEbayItemSpecificOption(row, preferred)) filled.push(row.key);
  }
  return filled;
}
function inferredItemSpecifics(pkg) {
  const specifics = { ...(pkg.item_specifics || {}) };
  const title = String(pkg.title || "");
  if (!specifics.Type && /\bhose\b/i.test(title)
      && !/\b(nozzle|adapter|adaptor|splitter|connector|repair|mender|timer|controller|reel|holder|fitting|valve|sprinkler|kit|set)\b/i.test(title)) {
    if (/\bexpand(?:ing|able)\b/i.test(title)) specifics.Type = "Expanding Hose";
    else if (/\bsoaker\b/i.test(title)) specifics.Type = "Soaker Hose";
    else if (/\bflat\b/i.test(title)) specifics.Type = "Flat Hose";
    else if (/\bgarden\b|\bheavy[ -]duty\b/i.test(title)) specifics.Type = "Standard Garden Hose";
  }
  const description = stripListingHtml(pkg.description || "");
  const source = `${title} ${description} ${String(pkg.source_url || "")}`;
  if (!specifics.Type && /\bwet[\s/&-]*dry\b[\s\S]{0,40}\bvacuum\b|\bvacuum\b[\s\S]{0,40}\bwet[\s/&-]*dry\b/i.test(source)) {
    specifics.Type = "Handheld";
  }
  if (!specifics["Battery Included"] && /\bcharger(?:s)?\b/i.test(source)) {
    specifics["Battery Included"] = "No";
  } else if (
    !specifics["Battery Included"] &&
    /\b(?:battery included|includes?\s+(?:an?\s+|\d+\s+)?batter(?:y|ies)|with\s+(?:an?\s+|\d+\s+)?batter(?:y|ies))\b/i.test(source)
  ) {
    specifics["Battery Included"] = "Yes";
  }
  if (!specifics.Voltage) {
    const voltages = [...source.matchAll(/\b(\d{1,3}(?:\.\d+)?)\s*[- ]?\s*v(?:olt(?:s)?)?\b/gi)]
      .map((match) => Number(match[1]))
      .filter((voltage) => Number.isFinite(voltage) && voltage > 0);
    if (voltages.length) specifics.Voltage = `${Math.max(...voltages)} V`;
  }
  return specifics;
}
function itemSpecificMatches(key, value) {
  const expectedKey = normalizeText(key);
  const expectedValue = normalizeComparableValue(value);
  if (!expectedKey || !expectedValue) return false;
  const controls = [...document.querySelectorAll('button[name^="attributes."], input, textarea')].filter(isVisible);
  return controls.some((element) => {
    if (/search-box|extracted-attribute-selector/i.test(element.getAttribute("name") || "")) return false;
    const label = normalizeText([
      element.id,
      element.getAttribute("name"),
      element.getAttribute("aria-label"),
      element.getAttribute("data-testid"),
      labelText(element),
    ].filter(Boolean).join(" "));
    const current = normalizeComparableValue(element.value || element.innerText || element.textContent || "");
    return Boolean(current) && label.includes(expectedKey) && (current === expectedValue);
  });
}
if(!location.href.includes('draftId=5165219480001')||!document.title.includes('Faucet Adapter 2MQC'))throw Error('Wrong product');
const pkg={"product_id": 166, "sku": "SRC-465347BDE7", "title": "Faucet Adapter 2MQC | FREE SHIPPING", "price": 13.53, "quantity": 1, "condition": "New", "description": "<div data-autozs-template=\"1\" style=\"max-width:900px;margin:0 auto;background:#f6f8f7;border:1px solid #d9e2dd;font-family:Arial,Helvetica,sans-serif;color:#18201b;\"><div style=\"background:#14201c;color:#ffffff;padding:24px 28px;\"><div style=\"font-size:26px;font-weight:800;\">Anim59 Home Improvement</div><div style=\"margin-top:4px;color:#a9d8cf;font-size:13px;\">a.m.anim-59</div></div><div style=\"display:flex;flex-wrap:wrap;background:#55b7a7;color:#ffffff;\"><div style=\"flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;\">Fast shipping</div><div style=\"flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;\">30-day support</div><div style=\"flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;\">Responsive service</div></div><div style=\"padding:26px 28px;\"><h1 style=\"margin:0 0 20px;font-size:24px;line-height:1.3;\">Melnor Faucet Adapter 2MQC</h1><div style=\"background:#ffffff;border:1px solid #d9e2dd;border-radius:6px;padding:20px;line-height:1.6;\"><h2>Melnor Faucet Adapter 2MQC</h2><h3>Overview</h3><p>Enables speedy hose connections to adapt standard outdoor faucets</p><h3>Highlights</h3><ul><li>Compatible with the Melnor faucet end connector</li><li>Durable design</li></ul><h3>Details</h3><ul></ul><p>Please review all item specifics, shipping settings, returns, and compatibility before publishing.</p></div><div style=\"display:flex;flex-wrap:wrap;gap:12px;margin-top:18px;\"><div style=\"flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;background:#ffffff;\"><h3 style=\"margin:0 0 8px;color:#176f62;font-size:16px;\">About us</h3><p style=\"margin:0;color:#46524c;line-height:1.55;\">We source useful home improvement products and prepare every listing with clear product details, reliable service, and responsive support.</p></div><div style=\"flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;background:#ffffff;\"><h3 style=\"margin:0 0 8px;color:#176f62;font-size:16px;\">Shipping</h3><p style=\"margin:0;color:#46524c;line-height:1.55;\">Orders are processed promptly and shipped to the address provided at checkout. Delivery estimates can vary by destination, carrier conditions, weather, and supplier availability.</p></div><div style=\"flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;background:#ffffff;\"><h3 style=\"margin:0 0 8px;color:#176f62;font-size:16px;\">Returns</h3><p style=\"margin:0;color:#46524c;line-height:1.55;\">Returns are accepted according to the return policy shown on this listing. Items should be returned in the same condition received unless the item arrived damaged or incorrect.</p></div><div style=\"flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;background:#ffffff;\"><h3 style=\"margin:0 0 8px;color:#176f62;font-size:16px;\">Satisfaction</h3><p style=\"margin:0;color:#46524c;line-height:1.55;\">If there is a problem with your order, message us through eBay so we can help make it right.</p></div></div></div></div>", "item_specifics": {"Brand": "Melnor", "MPN": "301859820"}, "image_urls": ["https://images.thdstatic.com/productImages/976ff37f-ecdd-4af8-a4cc-de6dc7402ee8/svn/melnor-hose-fittings-2mqc-64_1000.jpg", "https://images.thdstatic.com/productImages/bb2223be-fe38-4801-be58-6781201efa85/svn/melnor-hose-fittings-2mqc-4f_100.jpg", "https://images.thdstatic.com/productImages/cf17f9c1-01c4-42b6-936e-2a29cb67f764/svn/melnor-hose-fittings-2mqc-31_100.jpg", "https://images.thdstatic.com/productImages/345918b5-8485-4969-8862-d1bc002b6ca2/svn/melnor-hose-fittings-2mqc-c3_600.jpg"], "local_image_paths": ["downloads/product_images/166/edited/01.jpg", "downloads/product_images/166/edited/02.jpg", "downloads/product_images/166/edited/03.jpg", "downloads/product_images/166/edited/04.jpg"], "manual_image_paths": ["downloads/product_images/166/edited/01.jpg", "downloads/product_images/166/edited/02.jpg", "downloads/product_images/166/edited/03.jpg", "downloads/product_images/166/edited/04.jpg"], "image_upload_status": "ready", "source_url": "https://www.homedepot.com/p/Melnor-Faucet-Adapter-2MQC/301859820", "source_price": 8.28, "minimum_order_quantity": 1, "source_order_subtotal": 8.28, "source_shipping": 0.0, "landed_cost": 8.94, "effective_source_cost": 8.94, "gift_card_discount_enabled": false, "gift_card_discount_percent": 6.0, "sales_tax_percent": 8.0, "sales_tax_cost": 0.66, "competitor_price": null, "margin_price": 11.12, "competitor_target_price": null, "minimum_profit_price": 12.96, "safe_competitor_price": 12.96, "fee_rate_total": 0.156, "estimated_fees": 2.11, "estimated_profit": 2.48, "minimum_profit": 2.0, "profit_gap": 0.0, "meets_minimum_profit": true, "margin_price_profit": 0.45, "competitor_target_profit": null, "minimum_profit_price_profit": 2.0, "safe_competitor_price_profit": 2.0, "warnings": [], "pricing_strategy": "margin", "price_reason": "Margin pricing: source cost plus configured margin and total fee assumptions; raised to the minimum-profit guard; rounded up to 0.53", "offers_enabled": false, "listing_schedule_mode": "now", "listing_schedule_at": null, "shipping_cost_type": "flat", "domestic_shipping_service": "Economy Shipping", "buyer_shipping_cost": 0.0, "manual_posting_steps": ["Open eBay seller listing creation.", "Paste the title into the title field.", "Paste the calculated price into the price field.", "Paste the HTML description into the description field.", "Review and fill item specifics using item_specifics.", "Upload every usable downloaded local image from manual_image_paths.", "Disable offers unless offers_enabled is true.", "Schedule the listing at listing_schedule_at when a default schedule is configured.", "Use item condition New during eBay prelist.", "Use flat domestic shipping with buyer_shipping_cost and domestic_shipping_service.", "Review category, item specifics, shipping, returns, and quantity before publishing."]};await revealEbayItemSpecifics();const filled=await fillRequiredEbayItemSpecifics(pkg);return {filled,valid:requiredItemSpecificsSatisfied(),type:document.querySelector('button[name="attributes.Type"]')?.innerText,brand:document.querySelector('button[name="attributes.Brand"]')?.innerText};}catch(e){return {error:String(e)}}}});})()