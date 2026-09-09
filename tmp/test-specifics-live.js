(async()=>{const t=(await chrome.tabs.query({url:"https://www.ebay.com/lstng*"}))[0];return await chrome.scripting.executeScript({target:{tabId:t.id},func:async()=>{function itemSpecificMatches(key, value) {
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
const pkg={"product_id": 104, "sku": "SRC-40675AADA2", "title": "5/8 in. x 50 ft. Heavy-Duty Hose | FREE SHIPPING", "price": 41.53, "quantity": 1, "condition": "New", "description": "<div data-autozs-template=\"1\" style=\"max-width:900px;margin:0 auto;background:#f6f8f7;border:1px solid #d9e2dd;font-family:Arial,Helvetica,sans-serif;color:#18201b;\"><div style=\"background:#14201c;color:#ffffff;padding:24px 28px;\"><div style=\"font-size:26px;font-weight:800;\">Anim59 Home Improvement</div><div style=\"margin-top:4px;color:#a9d8cf;font-size:13px;\">a.m.anim-59</div></div><div style=\"display:flex;flex-wrap:wrap;background:#55b7a7;color:#ffffff;\"><div style=\"flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;\">Fast shipping</div><div style=\"flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;\">30-day support</div><div style=\"flex:1 1 160px;padding:13px 18px;text-align:center;font-weight:700;\">Responsive service</div></div><div style=\"padding:26px 28px;\"><h1 style=\"margin:0 0 20px;font-size:24px;line-height:1.3;\">Husky 5/8 in. x 50 ft. Heavy-Duty Hose</h1><div style=\"background:#ffffff;border:1px solid #d9e2dd;border-radius:6px;padding:20px;line-height:1.6;\"><h2>Husky 5/8 in. x 50 ft. Heavy-Duty Hose</h2><h3>Overview</h3><p>Crush proof brass thread couplings to prevent corrosion</p><h3>Highlights</h3><ul><li>Flexible collar for easy connection</li><li>Durable abrasion and UV resistant jacket</li></ul><h3>Details</h3><ul></ul><p>Please review all item specifics, shipping settings, returns, and compatibility before publishing.</p></div><div style=\"display:flex;flex-wrap:wrap;gap:12px;margin-top:18px;\"><div style=\"flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;background:#ffffff;\"><h3 style=\"margin:0 0 8px;color:#176f62;font-size:16px;\">About us</h3><p style=\"margin:0;color:#46524c;line-height:1.55;\">We source useful home improvement products and prepare every listing with clear product details, reliable service, and responsive support.</p></div><div style=\"flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;background:#ffffff;\"><h3 style=\"margin:0 0 8px;color:#176f62;font-size:16px;\">Shipping</h3><p style=\"margin:0;color:#46524c;line-height:1.55;\">Orders are processed promptly and shipped to the address provided at checkout. Delivery estimates can vary by destination, carrier conditions, weather, and supplier availability.</p></div><div style=\"flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;background:#ffffff;\"><h3 style=\"margin:0 0 8px;color:#176f62;font-size:16px;\">Returns</h3><p style=\"margin:0;color:#46524c;line-height:1.55;\">Returns are accepted according to the return policy shown on this listing. Items should be returned in the same condition received unless the item arrived damaged or incorrect.</p></div><div style=\"flex:1 1 210px;border:1px solid #d9e2dd;border-radius:6px;padding:14px;background:#ffffff;\"><h3 style=\"margin:0 0 8px;color:#176f62;font-size:16px;\">Satisfaction</h3><p style=\"margin:0;color:#46524c;line-height:1.55;\">If there is a problem with your order, message us through eBay so we can help make it right.</p></div></div></div></div>", "item_specifics": {"Brand": "Husky", "MPN": "CHDHKT58050"}, "image_urls": ["https://images.thdstatic.com/productImages/dc8f978d-3ecc-4033-94cd-09c35ae09061/svn/husky-garden-hoses-chdhkt58050-64_1000.jpg", "https://images.thdstatic.com/productImages/9cbdeeaf-93f9-4f00-b229-aca382655776/svn/husky-garden-hoses-chdhkt58050-40_100.jpg", "https://images.thdstatic.com/productImages/f0f7a9d1-cd8c-4959-bbf4-5384d7a99c1b/svn/husky-garden-hoses-chdhkt58050-a0_100.jpg", "https://images.thdstatic.com/productImages/d9fe89c8-854a-43fc-9a16-62f7b9192451/svn/husky-garden-hoses-chdhkt58050-1d_100.jpg", "https://images.thdstatic.com/productImages/e460bc59-d082-40c8-9197-0b954469fe1a/svn/husky-garden-hoses-chdhkt58050-c3_100.jpg", "https://images.thdstatic.com/productImages/730359c8-4263-4c0b-a2d1-b358eaeb2960/svn/husky-garden-hoses-chdhkt58050-4f_100.jpg", "https://images.thdstatic.com/productImages/5be0d832-cdb5-4123-bb3b-e5f0bbaf9cab/svn/husky-garden-hoses-chdhkt58050-1f_100.jpg", "https://images.thdstatic.com/productImages/58a2e5ad-872d-41d7-92d5-5b867f07eee0/svn/husky-garden-hoses-chdhkt58050-44_100.jpg", "https://images.thdstatic.com/productImages/ab609ca0-ff3f-4e3c-a1eb-079dcba648e1/svn/husky-garden-hoses-chdhkt58050-fa_100.jpg", "https://images.thdstatic.com/productImages/76513f29-9feb-45dc-abe2-f96d510d8be3/svn/husky-garden-hoses-chdhkt58050-76_100.jpg", "https://images.thdstatic.com/productImages/e90d34cd-8996-46ce-a1b7-add435222055/svn/husky-garden-hoses-chdhkt58050-31_100.jpg", "https://images.thdstatic.com/productImages/6390f5a1-a6ba-42f8-ada3-1a8a8bc105c5/svn/husky-garden-hoses-chdhkt58050-e1_600.jpg"], "local_image_paths": ["downloads/product_images/104/edited/01.jpg", "downloads/product_images/104/edited/02.jpg", "downloads/product_images/104/edited/03.jpg", "downloads/product_images/104/edited/04.jpg", "downloads/product_images/104/edited/05.jpg", "downloads/product_images/104/edited/06.jpg", "downloads/product_images/104/edited/07.jpg", "downloads/product_images/104/edited/08.jpg", "downloads/product_images/104/edited/09.jpg", "downloads/product_images/104/edited/10.jpg", "downloads/product_images/104/edited/11.jpg", "downloads/product_images/104/edited/12.jpg"], "manual_image_paths": ["downloads/product_images/104/edited/01.jpg", "downloads/product_images/104/edited/02.jpg", "downloads/product_images/104/edited/03.jpg", "downloads/product_images/104/edited/04.jpg", "downloads/product_images/104/edited/05.jpg", "downloads/product_images/104/edited/06.jpg", "downloads/product_images/104/edited/07.jpg", "downloads/product_images/104/edited/08.jpg", "downloads/product_images/104/edited/09.jpg", "downloads/product_images/104/edited/10.jpg", "downloads/product_images/104/edited/11.jpg", "downloads/product_images/104/edited/12.jpg"], "image_upload_status": "ready", "source_url": "https://www.homedepot.com/p/Husky-5-8-in-x-50-ft-Heavy-Duty-Hose-CHDHKT58050/326184162", "source_price": 29.98, "minimum_order_quantity": 1, "source_order_subtotal": 29.98, "source_shipping": 0.0, "landed_cost": 32.38, "effective_source_cost": 32.38, "gift_card_discount_enabled": false, "gift_card_discount_percent": 6.0, "sales_tax_percent": 8.0, "sales_tax_cost": 2.4, "competitor_price": null, "margin_price": 40.28, "competitor_target_price": null, "minimum_profit_price": 40.73, "safe_competitor_price": 40.73, "fee_rate_total": 0.156, "estimated_fees": 6.48, "estimated_profit": 2.67, "minimum_profit": 2.0, "profit_gap": 0.0, "meets_minimum_profit": true, "margin_price_profit": 1.62, "competitor_target_profit": null, "minimum_profit_price_profit": 2.0, "safe_competitor_price_profit": 2.0, "warnings": [], "pricing_strategy": "margin", "price_reason": "Margin pricing: source cost plus configured margin and total fee assumptions; raised to the minimum-profit guard; rounded up to 0.53", "offers_enabled": false, "listing_schedule_mode": "now", "listing_schedule_at": null, "shipping_cost_type": "flat", "domestic_shipping_service": "Economy Shipping", "buyer_shipping_cost": 0.0, "manual_posting_steps": ["Open eBay seller listing creation.", "Paste the title into the title field.", "Paste the calculated price into the price field.", "Paste the HTML description into the description field.", "Review and fill item specifics using item_specifics.", "Upload every usable downloaded local image from manual_image_paths.", "Disable offers unless offers_enabled is true.", "Schedule the listing at listing_schedule_at when a default schedule is configured.", "Use item condition New during eBay prelist.", "Use flat domestic shipping with buyer_shipping_cost and domestic_shipping_service.", "Review category, item specifics, shipping, returns, and quantity before publishing."]};if(!document.title.includes("50 ft."))throw Error("Wrong draft title");return {filled:await fillRequiredEbayItemSpecifics(pkg),type:document.querySelector('button[name="attributes.Type"]')?.innerText, matches:itemSpecificMatches("Type","Standard Garden Hose")};}})})()